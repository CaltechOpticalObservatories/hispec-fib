"""
HISPEC Lightpath Manager — core graph + spectra/throughput model (rev7)

Python 3.12 compatible.
This revision:
- Fixes Focus retro path to route **RETRO_in → IN_out** (gated) and updates external links accordingly.
- Moves spectral shapes to **synphot-first** wrappers (SourceSpectrum, SpectralElement, and models: Box1D, Gaussian1D, Empirical1D) with graceful fallbacks.
- Adds **TransmissionCurve.from_tabulated(...)** and **tc_from_file(...)** for file-based dichroic curves.
- Implements ATC selector (J/H/JH/JHgap) and CSD split using synphot Box1D-based bandpasses (placeholders until files provided).
- Keeps fiber **coupling coefficients** and wires an ATC Imager **QE curve** using synphot Box1D.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, Iterable, List, Optional, Tuple, Set
import bisect
import numpy as np

import scipy
import astropy.units as u
from astropy import constants as const
# from specutils import Spectrum1D
from synphot import SpectralElement, SourceSpectrum
from synphot import models as synmodels
from astropy.modeling import models as amodels


# =====================================================================================
# Scalar curves & spectra (thin wrappers)
# =====================================================================================
class TransmissionCurve:
    """Thin wrapper around a synphot SpectralElement (dimensionless throughput)."""

    def __init__(self, se: SpectralElement | float) -> None:
        self.se = se

    # ---- constructors ----

    @staticmethod
    def box(l0_nm: float, l1_nm: float, *, top: float = 1.0) -> TransmissionCurve:
        """Box passband using synphot.models.Box1D (no fallback)."""
        center = 0.5*(l0_nm + l1_nm)*u.nm
        width  = (l1_nm - l0_nm)*u.nm
        return TransmissionCurve.from_synphot_model(synmodels.Box1D, amplitude=top, x_0=center, width=width)

    @staticmethod
    def unity() -> "TransmissionCurve":
        return TransmissionCurve.constant(1.0)

    @staticmethod
    def constant(v: float) -> "TransmissionCurve":
        return TransmissionCurve.from_synphot_model(amodels.Const1D, amplitude=v)

    @staticmethod
    def zero() -> "TransmissionCurve":
        return TransmissionCurve.constant(0.0)

    @staticmethod
    def from_spectral_element(se: SpectralElement) -> "TransmissionCurve":
        return TransmissionCurve(se)

    @staticmethod
    def from_synphot_model(model: object, **kwargs) -> "TransmissionCurve":
        return TransmissionCurve(SpectralElement(model, **kwargs))

    @staticmethod
    def from_tabulated(wavelength_nm: list|np.ndarray, throughput: list|np.ndarray) -> "TransmissionCurve":
        assert len(wavelength_nm) == len(throughput)
        return TransmissionCurve.from_synphot_model(synmodels.Empirical1D,
                                                    points=np.asarray(wavelength_nm, dtype=float) * u.nm,
                                                    lookup_table=np.asarray(throughput, dtype=float))

    # ---- evaluation ----
    def __call__(self, wavelength_nm):
        return self.se(wavelength_nm * u.nm)

    # ---- composition ----
    def __mul__(self, other: "TransmissionCurve") -> "TransmissionCurve":
        return TransmissionCurve(self.se * other.se)

    __rmul__ = __mul__

    @staticmethod
    def product(curves: Iterable["TransmissionCurve"]) -> "TransmissionCurve":
        curves = list(curves)
        if not curves:
            return TransmissionCurve.unity()
        se = curves[0].se
        for c in curves[1:]:
            se = se * c.se
        return TransmissionCurve(se)

    def complement(self) -> "TransmissionCurve":

        one = amodels.Const1D(1.0)
        comp_model = one - self.se.model  # astropy model arithmetic
        return TransmissionCurve.from_synphot_model(comp_model)

    @staticmethod
    def envelope(curves: Iterable["TransmissionCurve"], grid_nm: np.ndarray) -> "TransmissionCurve":
        """
        Pointwise maximum across curves on the supplied wavelength grid (nm).

        This is the correct "selector union": at each λ, pick the best transmission
        available from any of the candidate elements (no mixing, no stacking).

        Args
        ----
        curves : Iterable[TransmissionCurve]
            The candidate transmission curves.
        grid_nm : array-like (float)
            Wavelength grid in nanometers on which to evaluate and build the result.

        Returns
        -------
        TransmissionCurve
            A new curve backed by synphot Empirical1D with values clipped to [0, 1].
        """
        curves = list(curves)
        if not curves:
            return TransmissionCurve.constant(0.0)

        grid_nm = np.asarray(grid_nm, dtype=float) * u.nm
        # Evaluate each curve on the grid; ensure plain floats
        vals = []
        for c in curves:
            y = c(grid_nm)
            vals.append(np.asarray(y, dtype=float))

        y_max = np.maximum.reduce(vals)
        y_max = np.clip(y_max, 0.0, 1.0)

        # Build a synphot SpectralElement from samples (dimensionless throughput)
        return TransmissionCurve.from_tabulated(grid_nm, y_max)



class Spectrum:
    """
    Thin wrapper around synphot SourceSpectrum ONLY.

    - Call with photons=False  -> returns density  (photons/s/nm) on the requested grid
    - Call with photons=True   -> returns per-bin  (photons/s)   integrated over each grid cell

    The 'is_density' flag declares what the underlying SourceSpectrum returns
    when evaluated in our unit system. If your model already yields per-bin photons/s,
    set is_density=False and we'll avoid double-integrating.

    Notes
    -----
    * We do not attempt unit gymnastics; we assume your SourceSpectrum has been
      constructed so that `ss(lam)` numerically matches the intended quantity
      (usually photons/s/nm). If needed, pre-wrap with a unit-converting model.
    """

    def __init__(self, ss: SourceSpectrum, *, width_hint_nm:float=None) -> None:
        if not isinstance(ss, SourceSpectrum):
            raise TypeError("Spectrum requires a synphot.SourceSpectrum")
        self.ss = ss
        self.width_hint_nm = width_hint_nm

    @staticmethod
    def _bin_widths(grid_nm: np.ndarray) -> np.ndarray:
        g = np.asarray(grid_nm, dtype=float)
        if g.ndim != 1 or g.size < 2:
            raise ValueError("grid_nm must be 1D with at least 2 samples")
        d = np.diff(g)
        w = np.empty_like(g)
        w[1:-1] = 0.5*(d[:-1] + d[1:])
        w[0]    = 0.5*d[0]
        w[-1]   = 0.5*d[-1]
        return w

    def evaluate_on(self, grid_nm: np.ndarray|u.Quantity) -> np.ndarray:
        """Raw evaluation of the underlying SourceSpectrum on grid_nm (nm)."""

        try:
            grid_nm = grid_nm.to(u.nm)
        except AttributeError:
            grid_nm = np.asarray(grid_nm, dtype=float) * u.nm
        # synphot returns a Quantity; we coerce to plain float for pipeline math
        y = self.ss(grid_nm).to('ph/(cm2 nm s)')
        return np.asarray(y, dtype=float)

    def __call__(self, grid_nm: np.ndarray, *, photons: bool = False) -> np.ndarray:
        """
        photons=False -> photons/s/nm (density)
        photons=True  -> photons/s     (per bin centered on each grid sample)
        """
        y = self.evaluate_on(grid_nm)
        if photons:
            return y*self._bin_widths(grid_nm)
        else:
            return y
            # # per-bin stored but density requested: produce an approximate density
            # w = self._bin_widths(grid_nm)
            # with np.errstate(divide="ignore", invalid="ignore"):
            #     d = np.where(w > 0, y/w, 0.0)
            # return d

    def __add__(self, other: Spectrum) -> Spectrum:
        return Spectrum(self.ss + other.ss)

    def __mul__(self, x: float | TransmissionCurve) -> "Spectrum":
        v = x if isinstance(x, float) else x.se
        return Spectrum(self.ss * v)
    __rmul__ = __mul__


# =====================================================================================
# Ports & Edges
# =====================================================================================
class PortDirection(str, Enum):
    IN = "in"
    OUT = "out"


@dataclass(frozen=True)
class Port:
    owner: "Component"
    name: str
    direction: PortDirection

    def fqname(self) -> str:
        return f"{self.owner.name}.{self.name}"


@dataclass
class Edge:
    src: Port
    dst: Port
    tcurve: TransmissionCurve = field(default_factory=TransmissionCurve.unity)
    active_pred: Optional[Callable[[], bool]] = None

    def active(self) -> bool:
        return True if self.active_pred is None else bool(self.active_pred())

    def __repr__(self):
        active = '' if self.active() else ' (inactive)'
        return f"{self.src.owner.name}.{self.src.name}->{self.dst.owner.name}.{self.dst.name}{active}"


# =====================================================================================
# Component base
# =====================================================================================
class Component:
    """Base class for all lightpath components.

    Components own ports and define *internal* edges that reflect their current state.
    External wiring is maintained by the LightpathManager via separate edges.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.ports: Dict[str, Port] = {}

    # -- Port helpers --
    def add_port(self, name: str, direction: PortDirection) -> Port:
        if name in self.ports:
            raise ValueError(f"Port already exists: {self.name}.{name}")
        p = Port(self, name, direction)
        self.ports[name] = p
        return p

    def port(self, name: str) -> Port:
        return self.ports[name]

    def internal_edges(self) -> Iterable[Edge]:
        return []


class BiPortMixin:
    """Utility to create per‑physical‑port IN/OUT pairs (e.g., A_in/A_out)."""

    def _add_pair(self, base: str) -> Tuple[Port, Port]:
        pin = self.add_port(f"{base}_in", PortDirection.IN)
        pout = self.add_port(f"{base}_out", PortDirection.OUT)
        return pin, pout


# =====================================================================================
# Simple components & switches
# =====================================================================================
class Fiber(Component):
    """Lossy 1‑in / 1‑out fiber segment with intrinsic transmission curve and coupling coefficient."""

    def __init__(self, name: str, transmission: TransmissionCurve | None = None, coupling: float = 1.0) -> None:
        super().__init__(name)
        self.in_p = self.add_port("in", PortDirection.IN)
        self.out_p = self.add_port("out", PortDirection.OUT)
        self.transmission = transmission or TransmissionCurve.unity()
        self.coupling = max(0.0, float(coupling))

    def set_coupling(self, value: float) -> None:
        self.coupling = max(0.0, float(value))

    def internal_edges(self) -> Iterable[Edge]:
        tcurve = TransmissionCurve.constant(self.coupling) * self.transmission
        yield Edge(self.in_p, self.out_p, tcurve)


class VariableAttenuator(Fiber):
    """Fiber with adjustable scalar attenuation (0..1 or dB)."""

    def __init__(self, name: str, initial: float = 1.0) -> None:
        super().__init__(name)
        self._linear = max(0.0, min(1.0, float(initial)))

    def set_linear(self, value: float) -> None:
        self._linear = max(0.0, min(1.0, float(value)))

    def set_db(self, db: float) -> None:
        linear = 10.0 ** (-(float(db)) / 10.0)
        self.set_linear(linear)

    def internal_edges(self) -> Iterable[Edge]:
        tcurve = TransmissionCurve.constant(self._linear)
        yield Edge(self.in_p, self.out_p, tcurve)


class Switch(Component, BiPortMixin):
    """Unified fiber switch with labeled ports and directional pairs.

    Example states:
      - 1→2: allowed_edges = [("C","A"), ("C","B")]
      - 2→1: allowed_edges = [("A","C"), ("B","C")]
    """

    def __init__(self, name: str, labels: Iterable[str], allowed_edges: Iterable[Tuple[str, str]],
                 default: Tuple[str, str], transmission : Optional[Dict[Tuple[str, str], TransmissionCurve]] = None) -> None:
        super().__init__(name)
        self.labels = list(labels)
        self.pairs: Dict[str, Tuple[Port, Port]] = {}
        for lab in self.labels:
            self.pairs[lab] = self._add_pair(lab)
        self.allowed = list(allowed_edges)
        if default not in self.allowed:
            raise ValueError("default must be in allowed_edges")
        self.state: Tuple[str, str] = default
        self.transmission: Dict[Tuple[str, str], TransmissionCurve] = transmission or {}
        for k in list(self.transmission):
            if k not in self.allowed:
                self.transmission.pop(k, None)
        for k in self.allowed:
            if k not in self.transmission:
                self.transmission[k] = TransmissionCurve.unity()

    @classmethod
    def one_to_many(cls, name: str, common: str, choices: Iterable[str], default_choice: str,
                    transmission : Optional[Dict[Tuple[str, str], TransmissionCurve]] = None) -> "Switch":
        choices = list(choices)
        allowed = [(common, c) for c in choices]
        return cls(name, labels=[common] + choices, allowed_edges=allowed, default=(common, default_choice),
                   transmission=transmission)

    @classmethod
    def many_to_one(cls, name: str, common: str, choices: Iterable[str], default_choice: str,
                    transmission : Optional[Dict[Tuple[str, str], TransmissionCurve]] = None) -> "Switch":
        choices = list(choices)
        allowed = [(c, common) for c in choices]
        return cls(name, labels=[common] + choices, allowed_edges=allowed, default=(default_choice, common),
                   transmission=transmission)

    def set_state(self, src_label: str, dst_label: str) -> None:
        if (src_label, dst_label) not in self.allowed:
            raise ValueError(f"Illegal switch state {(src_label, dst_label)}")
        self.state = (src_label, dst_label)

    def internal_edges(self) -> Iterable[Edge]:
        src, dst = self.state
        src_in, _ = self.pairs[src]
        _, dst_out = self.pairs[dst]
        yield Edge(src_in, dst_out, self.transmission[self.state])


class OpticalBeam(Component):
    """Lossless N‑in → 1‑out combiner. Each input feeds the output."""

    def __init__(self, name: str, n_inputs: int) -> None:
        super().__init__(name)
        self.inputs: List[Port] = []
        for i in range(n_inputs):
            self.inputs.append(self.add_port(f"in{i+1}", PortDirection.IN))
        self.out = self.add_port("out", PortDirection.OUT)

    def internal_edges(self) -> Iterable[Edge]:
        for p in self.inputs:
            yield Edge(p, self.out, TransmissionCurve.unity())


class WavelengthDivisionMultiplexer(OpticalBeam):
    """N‑in → 1‑out WDM with per‑input transmission curves (directional in_i→out)."""

    def __init__(self, name: str, n_inputs: int, per_input: Optional[List[TransmissionCurve]] = None) -> None:
        super().__init__(name, n_inputs)
        self.per_input: List[TransmissionCurve] = per_input or [TransmissionCurve.unity() for _ in range(n_inputs)]
        if len(self.per_input) != n_inputs:
            raise ValueError("per_input length must match n_inputs")

    def set_input_curve(self, index: int, curve: TransmissionCurve) -> None:
        self.per_input[index] = curve

    def internal_edges(self) -> Iterable[Edge]:
        for p, tc in zip(self.inputs, self.per_input):
            yield Edge(p, self.out, tc)


class Filter(Component, BiPortMixin):
    """Two‑port optic with *directional* curves (A↔B)."""

    def __init__(self, name: str, t_AB: TransmissionCurve | None = None, t_BA: TransmissionCurve | None = None) -> None:
        super().__init__(name)
        self.A_in, self.A_out = self._add_pair("A")
        self.B_in, self.B_out = self._add_pair("B")
        self.t_AB = t_AB or TransmissionCurve.unity()
        self.t_BA = t_BA or TransmissionCurve.unity()

    def internal_edges(self) -> Iterable[Edge]:
        yield Edge(self.A_in, self.B_out, self.t_AB)
        yield Edge(self.B_in, self.A_out, self.t_BA)


class Dichroic(Component, BiPortMixin):
    """Three‑port dichroic with *directional* per‑pair curves."""

    def __init__(self, name: str, curves: Optional[Dict[Tuple[str, str], TransmissionCurve]] = None) -> None:
        super().__init__(name)
        self.A_in, self.A_out = self._add_pair("A")
        self.B_in, self.B_out = self._add_pair("B")
        self.C_in, self.C_out = self._add_pair("C")
        self.curves: Dict[Tuple[str, str], TransmissionCurve] = {}
        default = TransmissionCurve.unity()
        for x in ("A", "B", "C"):
            for y in ("A", "B", "C"):
                if x == y:
                    continue
                self.curves[(x, y)] = default
        if curves:
            self.curves.update(curves)

    def _pair(self, label: str) -> Tuple[Port, Port]:
        return {
            "A": (self.A_in, self.A_out),
            "B": (self.B_in, self.B_out),
            "C": (self.C_in, self.C_out),
        }[label]

    def internal_edges(self) -> Iterable[Edge]:
        for (x, y), tc in self.curves.items():
            x_in, _ = self._pair(x)
            _, y_out = self._pair(y)
            yield Edge(x_in, y_out, tc)


class DichroicSelector(Component, BiPortMixin):
    """Selector that swaps between multiple dichroic *models* (e.g., J/H/JH/JHgap).

    Exposes A/B/C `_in/_out` pairs; internal edges mirror the selected model’s curves.
    """

    def __init__(self, name: str, models: Dict[str, Dict[Tuple[str, str], TransmissionCurve]], default: str) -> None:
        super().__init__(name)
        self.A_in, self.A_out = self._add_pair("A")
        self.B_in, self.B_out = self._add_pair("B")
        self.C_in, self.C_out = self._add_pair("C")
        self._models = dict(models)
        if default not in self._models:
            raise ValueError("default model not in models")
        self._mode = default

    def set_state(self, name: str) -> None:
        if name not in self._models:
            raise ValueError(f"Unknown mode {name}")
        self._mode = name

    def internal_edges(self) -> Iterable[Edge]:
        curves = self._models[self._mode]
        mapping = {"A": (self.A_in, self.A_out), "B": (self.B_in, self.B_out), "C": (self.C_in, self.C_out)}
        for (x, y), tc in curves.items():
            x_in, _ = mapping[x]
            _, y_out = mapping[y]
            yield Edge(x_in, y_out, tc)


# Alias per naming preference
SelectableDichroic = DichroicSelector


class SelectableFilter(Component, BiPortMixin):
    """Selector that swaps between multiple 2‑port filter *models*.

    Each model can define directional curves for (A→B) and (B→A). If only one curve is
    provided, it is used in both directions.

    Supports an optional **reverse_enable_predicate** to conditionally allow the B→A edge.
    """

    def __init__(self, name: str, models: Dict[str, Dict[Tuple[str, str], TransmissionCurve]], default: str) -> None:
        super().__init__(name)
        self.A_in, self.A_out = self._add_pair("A")
        self.B_in, self.B_out = self._add_pair("B")
        self._models = dict(models)
        if default not in self._models:
            raise ValueError("default model not in models")
        self._mode = default
        self._reverse_enable_pred: Optional[Callable[[], bool]] = None

    def set_state(self, name: str) -> None:
        if name not in self._models:
            raise ValueError(f"Unknown mode {name}")
        self._mode = name

    def set_reverse_enable_predicate(self, pred: Callable[[], bool]) -> None:
        self._reverse_enable_pred = pred

    def internal_edges(self) -> Iterable[Edge]:
        curves = self._models[self._mode]
        t_ab = curves.get(("A", "B"), TransmissionCurve.unity())
        t_ba = curves.get(("B", "A"), t_ab)
        # Forward A→B always
        yield Edge(self.A_in, self.B_out, t_ab)
        # Reverse B→A conditionally
        if self._reverse_enable_pred is None:
            allow = True
        else:
            allow = bool(self._reverse_enable_pred())
        yield Edge(self.B_in, self.A_out, t_ba, active_pred=(lambda: allow))


class FocusSelector(Component, BiPortMixin):
    """Generic Focus selector.

    Forwards: routes IN → {MMF_out, SMF_out, SCI_out} per current state.
    Retro gating: RETRO_in → IN_out edge is active only when state ∈ {SMF, SCI}.
    """

    def __init__(self, name: str, default: str = "SMF") -> None:
        super().__init__(name)
        # Forward path ports
        self.IN_in, self.IN_out = self._add_pair("IN")
        self.MMF_in, self.MMF_out = self._add_pair("MMF")
        self.SMF_in, self.SMF_out = self._add_pair("SMF")
        self.SCI_in, self.SCI_out = self._add_pair("SCI")
        # Retro path ports (explicit for internal gating)
        self.RETRO_in, self.RETRO_out = self._add_pair("RETRO")
        if default not in ("MMF", "SMF", "SCI"):
            raise ValueError("default must be one of MMF, SMF, SCI")
        self.state = default

    def set_state(self, state: str) -> None:
        if state not in ("MMF", "SMF", "SCI"):
            raise ValueError("state must be one of MMF, SMF, SCI")
        self.state = state

    def _retro_enabled(self) -> bool:
        return self.state in ("SMF", "SCI")

    def internal_edges(self) -> Iterable[Edge]:
        # Forward IN → selected focus output
        dst_out = {"MMF": self.MMF_out, "SMF": self.SMF_out, "SCI": self.SCI_out}[self.state]
        yield Edge(self.IN_in, dst_out, TransmissionCurve.unity())
        # Retro path flows through the component: RETRO_in → IN_out (gated)
        yield Edge(self.RETRO_in, self.IN_out, TransmissionCurve.unity(), active_pred=self._retro_enabled)


# =====================================================================================
# Sources & Detectors
# =====================================================================================
class Source(Component):
    """Abstract source: one OUT port and an emission spectrum scaled by a drive level."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.out = self.add_port("out", PortDirection.OUT)

    def spectrum(self) -> Spectrum:
        pass


class LaserDiode(Source):
    """Laser diode as a Gaussian emission line using synphot.

    Accepts astropy quantities or plain numbers (nm/mA).
    """

    def __init__(self, name: str,
                 wavelength, width, threshold_current,
                 *, max_current=300*u.mA, dP_dI=0.15*u.W/u.A,
                 dlambda_dT=0*u.nm/u.deg_C, dlambda_dA=0*u.nm/u.A,
                 nominal_temperature=25*u.deg_C,
                 voltage=None, current_step=0.1*u.mA, tec_current=None):
        super().__init__(name)
        self._lambda0 = self._to_nm(wavelength) * u.nm
        self._fwhm   = self._to_nm_or_from_hz(width, center_nm=self._lambda0.to_value(u.nm)) * u.nm
        self.threshold_current = self._to_mA(threshold_current) * u.mA
        self.max_current       = self._to_mA(max_current) * u.mA
        self.current_step      = self._to_mA(current_step) * u.mA
        self.dP_dI = dP_dI
        self.dlambda_dT = dlambda_dT
        self.dlambda_dA = dlambda_dA
        self.voltage = voltage
        self.tec_current = tec_current
        self._current = self.threshold_current
        self._temperature_C = nominal_temperature
        self._nominal_temperature = nominal_temperature

    # helpers
    def _to_nm(self, x) -> float:
        return float(x.to_value(u.nm)) if hasattr(x, "to") else float(x)

    def _to_mA(self, x) -> float:
        return float(x.to_value(u.mA)) if hasattr(x, "to") else float(x)

    def _to_nm_or_from_hz(self, width, *, center_nm: float) -> float:
        if hasattr(width, "si") and width.si.unit == u.Hz:
            return float(((center_nm*u.nm)**2/const.c * width).to_value(u.nm))
        return self._to_nm(width)

    # interface
    def set_current(self, value) -> None:
        self._current = (value if hasattr(value, "to") else value*u.mA).to(u.mA)

    def set_temperature(self, value_celsius: float) -> None:
        self._temperature_C = float(value_celsius)

    def valid_drive_current_array(self):
        lo = self.threshold_current.to_value(u.mA)
        hi = self.max_current.to_value(u.mA)
        step = self.current_step.to_value(u.mA)
        return np.arange(lo, hi, step) * u.mA

    def spectrum(self, limit_R=200000) -> Spectrum:
        I = self._current
        if I < self.threshold_current or I > self.max_current:
            amp = 0
        else:
            P = (self.dP_dI * I.to(u.A)).to(u.W)                      # slope efficiency
            delta_T = self._temperature_C - self._nominal_temperature
            lam = self._lambda0 + self.dlambda_dT*delta_T + self.dlambda_dA*I.to(u.A)
            lam_nm = lam.to_value(u.nm)
            # photons/s = P * λ / (h c)
            N_ph_s = (P * lam.to(u.m) / (const.h*const.c)).to(1/u.s).value
            sigma_nm = max(lam_nm/limit_R, self._fwhm.to_value(u.nm) / (2.0*np.sqrt(2.0*np.log(2.0))))
            amp = float(N_ph_s) / (sigma_nm * np.sqrt(2.0*np.pi))
            print(P.to('mW'), N_ph_s, amp, lam_nm, sigma_nm)
        return Spectrum(SourceSpectrum(synmodels.Gaussian1D, amplitude=amp, mean=lam_nm*u.nm, stddev=sigma_nm*u.nm),
                        width_hint_nm=sigma_nm*u.nm)


class Detection:
    def __init__(self, levels, signal, noise, saturation, snr:Any=None):
        self.levels = levels
        self.signal = signal
        self.noise = noise
        self.saturation = saturation
        self.snr = snr if snr is not None else self.signal/np.sqrt(self.signal+self.noise**2)
        self.saturation_mask = self.signal >= self.saturation

    def sn(self, saturated=np.nan, collapse=np.max):
        snr = self.snr.copy()
        snr[self.saturation_mask] = saturated
        if snr.ndim ==1:
            return snr
        if collapse ==np.sum:
            return np.sqrt(collapse(snr**2, axis=0))
        else:
            return collapse(snr, axis=0)

class Detector(Component):
    pass

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.name}>"

class Photodiode(Detector):

    def __init__(self, name: str,
                 noise = 7.5 * u.femtowatt / u.Hz ** 0.5,
                 gain = 1e11 * u.V/u.A,
                 saturation = 110 * u.picowatt,
                 adc_noise=0.6 * u.mV / (10 * u.V),
                 saturation_wavelength = 1550 * u.nm,
                 resp_wavelength_nm: "np.ndarray | None" = None,
                 resp_values: "np.ndarray | None" = None) -> None:
        super().__init__(name)
        self.in_p = self.add_port("in", PortDirection.IN)

        # Detector noise model (simple, scalar)
        self.noise = noise
        self.saturation = saturation
        self.adc_noise = adc_noise
        self.gain = gain
        self.resp_wavelength_nm = resp_wavelength_nm
        self.resp_values = resp_values.to(u.A/u.W) if resp_values is not None else None
        self.saturation_wavelength = saturation_wavelength.value

        # responsivity in A/W
        self._resp_a_per_w = lambda grid_nm : np.interp(grid_nm, resp_wavelength_nm, self.resp_values.value).clip(0, np.inf)

    def observe(self, fluence: Spectrum, *, grid_nm: np.ndarray, texp_s: float = 1.0) -> "Detection":
        """
        Integrate electrons on a caller-supplied wavelength grid.

        Parameters
        ----------
        fluence : Spectrum
            Source spectrum. Its evaluate_on(grid) should yield photons/s/nm by default.
        grid_nm : array-like
            Wavelength grid in nm on which to evaluate.
        texp_s : float
            Exposure time in seconds.

        Returns
        -------
        Detection
            (levels, photons, noise, saturation_mask) — same structure you use today.
        """
        grid_nm = np.asarray(grid_nm, dtype=float)
        S = fluence(grid_nm, photons=True) * (const.h * const.c / (grid_nm*u.nm).to(u.m))/u.s # watts
        volts = ((S * self._resp_a_per_w(grid_nm)*u.A/u.W).sum() * self.gain).to('V')
        noise = (self.noise * (1 / 2/ (texp_s*u.s)) ** 0.5 * self._resp_a_per_w(self.saturation_wavelength) *u.A/u.W * self.gain).to('V')
        total_noise = np.hypot(noise, self.adc_noise*volts)
        saturation_v = (self.saturation*self.gain*self._resp_a_per_w(self.saturation_wavelength) *u.A/u.W).to('V')

        return Detection(levels=fluence, signal=volts, noise=total_noise, saturation=saturation_v, snr=volts/total_noise)


class Spectrograph(Detector):
    """Minimal stub spectrograph with one IN port (detailed detect() to be added)."""

    def __init__(self, name: str, orders_file: str, resolution_file:str, noise=6 * u.electron / u.pixel, trace_width=3,
                 saturation=100000, qe: TransmissionCurve | None = None) -> None:
        super().__init__(name)
        self.in_p = self.add_port("in", PortDirection.IN)

        self.orders = np.loadtxt(orders_file, delimiter=',',
                                 dtype=[('order', int), ('min_l', np.float64), ('max_l', np.float64)]).view(np.recarray)

        ## Order, Wavelength (nm), X Pos (mm), Y Pos (mm), Dispersion (nm/pix), FWHM (pix), Resolution
        self.res = np.loadtxt(resolution_file,
                              dtype=[('order', np.float64), ('l', np.float64), ('x', np.float64), ('y', np.float64),
                                     ('dispersion', np.float64), ('fwhm', np.float64),
                                     ('resolution', np.float64)]).view(np.recarray)
        self.noise = noise
        self.trace_width = trace_width
        self.qe = qe or TransmissionCurve.unity()
        self.saturation = saturation

    def _in_order(self, wavelength):
        return (self.orders.min_l < wavelength) & (wavelength < self.orders.max_l)

    def _pixels_per_res_elem(self, order_mask, wavelength:float=None):
        ppre = self.res[order_mask].wavelength/self.res[order_mask].resolution/self.res[order_mask].dispersion
        if wavelength is None:
            wave_ndx = np.argmin(np.abs(self.res[order_mask].wavelength-wavelength))
            ppre = ppre[wave_ndx]

        return ppre

    def observe(self, fluence: Spectrum, *, grid_nm: np.ndarray, texp_s: float = 1.0) -> dict[int,"Detection"]:

        photons = texp_s * fluence(grid_nm, photons=False)
        non_zero = photons>0

        nozero_wave = grid_nm[non_zero]

        mean_wave = (nozero_wave*photons[non_zero]).sum()/photons[non_zero].sum()

        found_in_order = self._in_order(mean_wave.value)
        if not found_in_order.any():
            print(f'{fluence} with mean wavelength of {mean_wave:1f} not found in any order in {self}')
            return None
            # zeros = u.Quantity(np.zeros_like(fluence))
            # return Detection(fluence, zeros, self.noise, self.saturation)

        result = {}
        for order in self.orders[found_in_order]:

            #Find the mean dispersion for the order
            in_res = self.res.order == order.order
            mean_resolution = self.res[in_res].resolution.mean()
            mean_dispersion = self.res[in_res].dispersion.mean() * u.nm / u.pixel

            #get the number of pixels in a resolution element at the wavelength,
            # the original point of this was as a hack for unresolved or marginally resolved sources
            # where all of the
            # pixels_per_res_elem = np.ceil(self._pixels_per_res_elem(in_res), mean_wave)

            # res_elem_pixels = np.ceil(fluence[0].mean / mean_resolution / dispersion)

            # # How many pixels are involved
            # diode_pixels = np.ceil(fluence[0].stddev * 2.354 / dispersion)

            trace_sigma = self.trace_width / 2 / np.sqrt(2) / scipy.special.erfinv(.98)
            net_pix_flux = scipy.special.erf((np.arange(self.trace_width / 2) + .5) / trace_sigma / np.sqrt(2))
            pix_frac = np.diff(net_pix_flux) / 2
            trace_flux_frac = np.concatenate((pix_frac[::-1], [net_pix_flux[0]], pix_frac))


            # spectral_pixels = min(diode_pixels*3, 4096 * u.pix)
            _, l0, l1 = order
            min_l = max(l0, grid_nm[non_zero].min().value)
            max_l = min(l1, grid_nm[non_zero].max().value)
            pixel_wave = np.arange(min_l, max_l+1.5*mean_dispersion.value/2, mean_dispersion.value)

            photons = np.interp(pixel_wave[:-1], grid_nm.value, photons)*np.diff(pixel_wave)

            photons_2d = (photons*trace_flux_frac[:, None]).reshape(-1, photons.shape[-1])

            result[int(order.order)] = Detection(fluence, photons_2d, (self.noise / u.electron*u.pix).value, self.saturation)

        return result


class Imager(Detector):
    """ATC imager stub: applies QE internally during `observe()` and renders a pixel array.

    This is intentionally lightweight; replace with full instrument model later.
    """

    def __init__(self, name: str, n_pixels: int = 13, fwhm_pix: float = 2.7, read_noise_e: float = 12.0, saturation_adu: float = 1e5,
                 qe: TransmissionCurve | None = None) -> None:
        super().__init__(name)
        self.in_p = self.add_port("in", PortDirection.IN)
        self.n = int(n_pixels)
        self.read_noise_e = float(read_noise_e)
        self.saturation = float(saturation_adu)
        self.qe = qe or TransmissionCurve.unity()
        # Build normalized 2D Gaussian PSF grid
        ax = np.linspace(-self.n / 2, self.n / 2, num=self.n)
        X, Y = np.meshgrid(ax, ax)
        sigma = max(1e-6, fwhm_pix / (2.0 * np.sqrt(2.0 * np.log(2.0))))
        spot = np.exp(-(X**2 + Y**2) / (2.0 * sigma**2))
        self.spot = spot / spot.sum()

    def observe(self, fluence: Spectrum, *, grid_nm: np.ndarray, texp_s: float = 1.0) -> "Detection":
        """Convert spectral fluence to an ADU image applying QE and simple read noise."""
        # Integrate photons via simple Riemann sum on a coarse grid — demo only
        grid_nm = np.asarray(grid_nm, dtype=float)
        flux = (fluence*self.qe)(grid_nm, photons=True)*float(texp_s)
        signal = flux.sum() * self.spot
        return Detection(fluence, signal, self.read_noise_e, self.saturation)


# =====================================================================================
# LightpathManager
# =====================================================================================
class LightpathManager:
    """Owns components and external wiring; computes feasible routes and propagations."""

    def __init__(self) -> None:
        self.components: Dict[str, Component] = {}
        self._links: List[Edge] = []

    # -- Component management --
    def add(self, comp: Component) -> Component:
        if comp.name in self.components:
            raise ValueError(f"Component already exists: {comp.name}")
        self.components[comp.name] = comp
        return comp

    def get(self, name: str) -> Component:
        return self.components[name]

    # -- Wiring --
    def link(self, src: Port, dst: Port, tcurve: TransmissionCurve | None = None) -> None:
        if src.direction != PortDirection.OUT:
            raise ValueError(f"link requires OUT src: {src.fqname()}")
        if dst.direction != PortDirection.IN:
            raise ValueError(f"link requires IN dst: {dst.fqname()}")
        self._links.append(Edge(src, dst, tcurve or TransmissionCurve.unity()))

    # -- Graph snapshot --
    def _active_edges(self) -> List[Edge]:
        edges: List[Edge] = []
        edges.extend(self._links)
        for c in self.components.values():
            for e in c.internal_edges():
                if e.active():
                    edges.append(e)
        return edges

    # -- Adjacency --
    def _adjacency(self) -> Dict[Port, List[Edge]]:
        adj: Dict[Port, List[Edge]] = {}
        for e in self._active_edges():
            adj.setdefault(e.src, []).append(e)
        return adj

    # -- Pathfinding --
    def find_path(self, src: Port, dst: Port) -> Optional[List[Edge]]:
        paths = self.find_all_paths(src, dst, max_paths=1)
        return paths[0] if paths else None

    def find_all_paths(self, src: Port, dst: Port, *, max_paths: int = 32, max_hops: int = 256) -> List[List[Edge]]:
        """Enumerate simple paths from src→dst (bounded to prevent explosion)."""
        adj = self._adjacency()
        results: List[List[Edge]] = []

        def dfs(node: Port, target: Port, visited: Set[Port], path: List[Edge]) -> None:
            if len(results) >= max_paths or len(path) >= max_hops:
                return
            if node == target:
                results.append(list(path))
                return
            for e in adj.get(node, []):
                v = e.dst
                if v in visited:
                    continue
                visited.add(v)
                path.append(e)
                dfs(v, target, visited, path)
                path.pop()
                visited.remove(v)

        dfs(src, dst, {src}, [])
        return results

    # -- Curves & propagation --
    def path_curve(self, path: List[Edge]) -> TransmissionCurve:
        return TransmissionCurve.product(e.tcurve for e in path)

    def propagate(self, source_ports: Dict[Port, Spectrum], detectors: Iterable[Detector], *, max_paths: int = 32) -> Dict[Detector, Spectrum]:
        """Compute spectra at each detector port by summing contributions over all paths.

        source_ports: map of *source OUT ports* to emitted spectra.
        detectors: iterable of *detectors*.
        Returns: dict mapping detector IN port → Spectrum.
        """
        out: Dict[Port, Spectrum] = {}
        for detector in detectors:
            d = detector.port("in")
            acc = None  # zero spectrum
            width_hint_nm = np.inf
            for s_port, S in source_ports.items():
                width_hint_nm = min(width_hint_nm, S.width_hint_nm if S.width_hint_nm is not None else np.inf)
                for path in self.find_all_paths(s_port, d, max_paths=max_paths):
                    T = self.path_curve(path)
                    acc = acc + (S * T) if acc is not None else S * T
            if acc is not None:
                acc.width_hint_nm = width_hint_nm if np.isfinite(width_hint_nm) else None
            out[detector] = acc
        return out


# =====================================================================================
# HISPEC: partial topology build (YJ branch + ATC selector, CSD, PIAA selector, Focus selector, ATC imager)
# =====================================================================================

# ---- Synphot-backed helpers ----

def tc_box(l0_nm: float, l1_nm: float, *, top: float = 1.0) -> TransmissionCurve:
    """Box passband using synphot.models.Box1D (no fallback)."""
    center = 0.5*(l0_nm + l1_nm)*u.nm
    width  = (l1_nm - l0_nm)*u.nm
    return TransmissionCurve.from_synphot_model(synmodels.Box1D, amplitude=top, x_0=center, width=width)


def tc_from_file(path: str, *, delimiter: Optional[str] = None) -> TransmissionCurve:
    """Load a tabulated throughput (λ[nm], T) from a file. Uses synphot Empirical1D when available."""
    data = np.loadtxt(path, delimiter=delimiter)
    if data.ndim != 2 or data.shape[1] < 2:
        raise ValueError("Expected a 2-column table: wavelength_nm, throughput")
    wav = data[:, 0]
    thr = data[:, 1]
    return TransmissionCurve.from_tabulated(wav, thr)


# ---- Topology ----

def build_hispec_partial() -> LightpathManager:
    """Create a LightpathManager per connectivity (YJ up to ATC/CSD/PIAA/FOCUS/ATC imager)."""

    ATC_QE = 0.82
    RSPEC_QE = 0.98
    BSPEC_QE = 0.92

    # Photodiode responsivity tables (A/W). We'll smooth with PCHIP to continuous curves.
    FEMTO_QE_TC = {900.: 0.2*u.A/u.W, 1000.: 0.6*u.A/u.W, 1040.: 0.68*u.A/u.W, 1200.: 0.8*u.A/u.W,
                   1270.: 0.85*u.A/u.W, 1430.: 0.93*u.A/u.W, 1500.: 0.95*u.A/u.W, 1600.: 0.93*u.A/u.W,
                   1700.: 0.2*u.A/u.W}
    FEMTO_QE_TC = tuple(map(u.Quantity, zip(*list(FEMTO_QE_TC.items()))))
    THOR_QE_TC = {
        1400.: 0.50199*u.A/u.W, 1410.: 0.51144*u.A/u.W, 1420.: 0.51867*u.A/u.W, 1430.: 0.5264*u.A/u.W,
        1440.: 0.5337*u.A/u.W, 1450.: 0.54358*u.A/u.W, 1460.: 0.55372*u.A/u.W, 1470.: 0.5643*u.A/u.W,
        1480.: 0.5746*u.A/u.W, 1490.: 0.58604*u.A/u.W, 1500.: 0.59885*u.A/u.W, 1510.: 0.60971*u.A/u.W,
        1520.: 0.62102*u.A/u.W, 1530.: 0.63428*u.A/u.W, 1540.: 0.64785*u.A/u.W, 1550.: 0.66118*u.A/u.W,
        1560.: 0.67499*u.A/u.W, 1570.: 0.68843*u.A/u.W, 1580.: 0.70238*u.A/u.W, 1590.: 0.71497*u.A/u.W,
        1600.: 0.7285*u.A/u.W, 1610.: 0.74146*u.A/u.W, 1620.: 0.75481*u.A/u.W, 1630.: 0.76951*u.A/u.W,
        1640.: 0.78517*u.A/u.W, 1650.: 0.79927*u.A/u.W, 1660.: 0.81352*u.A/u.W, 1670.: 0.82736*u.A/u.W,
        1680.: 0.84172*u.A/u.W, 1690.: 0.85701*u.A/u.W, 1700.: 0.87061*u.A/u.W, 1710.: 0.88342*u.A/u.W,
        1720.: 0.89808*u.A/u.W, 1730.: 0.91253*u.A/u.W, 1740.: 0.92943*u.A/u.W, 1750.: 0.94613*u.A/u.W,
        1760.: 0.96487*u.A/u.W, 1770.: 0.98363*u.A/u.W, 1780.: 1.00287*u.A/u.W, 1790.: 1.02496*u.A/u.W,
        1800.: 1.04875*u.A/u.W, 1810.: 1.06712*u.A/u.W, 1820.: 1.08436*u.A/u.W, 1830.: 1.10028*u.A/u.W,
        1840.: 1.11462*u.A/u.W, 1850.: 1.12724*u.A/u.W, 1860.: 1.13955*u.A/u.W, 1870.: 1.14782*u.A/u.W,
        1880.: 1.15491*u.A/u.W, 1890.: 1.16097*u.A/u.W, 1900.: 1.16611*u.A/u.W, 1910.: 1.17542*u.A/u.W,
        1920.: 1.18509*u.A/u.W, 1930.: 1.18763*u.A/u.W, 1940.: 1.19081*u.A/u.W, 1950.: 1.19343*u.A/u.W,
        1960.: 1.19673*u.A/u.W, 1970.: 1.20183*u.A/u.W, 1980.: 1.20729*u.A/u.W, 1990.: 1.21037*u.A/u.W,
        2000.: 1.21345*u.A/u.W, 2010.: 1.21642*u.A/u.W, 2020.: 1.21931*u.A/u.W, 2030.: 1.22209*u.A/u.W,
        2040.: 1.22468*u.A/u.W, 2050.: 1.22843*u.A/u.W, 2060.: 1.23213*u.A/u.W, 2070.: 1.23456*u.A/u.W,
        2080.: 1.23699*u.A/u.W, 2090.: 1.23941*u.A/u.W, 2100.: 1.24186*u.A/u.W, 2110.: 1.24433*u.A/u.W,
        2120.: 1.24566*u.A/u.W, 2130.: 1.24771*u.A/u.W, 2140.: 1.24979*u.A/u.W, 2150.: 1.25045*u.A/u.W,
        2160.: 1.25089*u.A/u.W, 2170.: 1.25113*u.A/u.W, 2180.: 1.25137*u.A/u.W, 2190.: 1.25029*u.A/u.W,
        2200.: 1.24917*u.A/u.W, 2210.: 1.24931*u.A/u.W, 2220.: 1.24955*u.A/u.W, 2230.: 1.24985*u.A/u.W,
        2240.: 1.25024*u.A/u.W, 2250.: 1.25124*u.A/u.W, 2260.: 1.25234*u.A/u.W, 2270.: 1.25041*u.A/u.W,
        2280.: 1.2472*u.A/u.W, 2290.: 1.24611*u.A/u.W, 2300.: 1.24395*u.A/u.W, 2310.: 1.24038*u.A/u.W,
        2320.: 1.23692*u.A/u.W, 2330.: 1.23378*u.A/u.W, 2340.: 1.22827*u.A/u.W, 2350.: 1.22241*u.A/u.W,
    }
    THOR_QE_TC = tuple(map(u.Quantity, zip(*list(THOR_QE_TC.items()))))

    def _placeholder_curves():
        return {
            ("A", "B"): TransmissionCurve.unity(),
            ("A", "C"): TransmissionCurve.unity(),
            ("C", "B"): TransmissionCurve.unity(),
        }

    ATC_DICHROIC_MODELS = {
        "J": _placeholder_curves(),
        "H": _placeholder_curves(),
        "JH": _placeholder_curves(),
        "JHgap": _placeholder_curves(),
    }

    CSD_DICHROIC_CURVES = {
        ("A", "B"): TransmissionCurve.unity(),
        ("A", "C"): TransmissionCurve.unity(),
        ("B", "A"): TransmissionCurve.unity(),
        ("C", "A"): TransmissionCurve.unity(),
    }

    PIAA_TC_BIDIR = {("A", "B"): TransmissionCurve.constant(.9),
                     ("B", "A"): TransmissionCurve.constant(.9)}
    VORTEX_TC_BIDIR = {("A", "B"): TransmissionCurve.constant(.3),
                       ("B", "A"): TransmissionCurve.constant(.3)}
    VORTEX_DARK_TC_BIDIR = {("A", "B"): TransmissionCurve.constant(3.2e-4),
                            ("B", "A"): TransmissionCurve.constant(3.2e-4)}
    NORMAL_FREESPACE_TC_BIDIR = {("A", "B"): TransmissionCurve.constant(.75),
                                 ("B", "A"): TransmissionCurve.constant(.75)}

    ECHELLE_ORDERS_FILE = {
        'yj': '/Users/jibailey/src/coo_playground/data/hispec_orders/orders_20220608C_HISPEC_SPECTRO_YJ_pyechelle.csv',
        'hk': '/Users/jibailey/src/coo_playground/data/hispec_orders/orders_20220608C_HISPEC_SPECTRO_HK_pyechelle.csv'}

    ECHELLE_RESOLUTION_FILE = {
        'yj': '/Users/jibailey/src/coo_playground/data/hispec_orders/BSPEC_Spectral_Resolution_v2.txt',
        'hk': '/Users/jibailey/src/coo_playground/data/hispec_orders/RSPEC_Spectral_Resolution_v2.txt'
    }

    lp = LightpathManager()

    # Sources
    s_1028 = lp.add(LaserDiode("LD1028", 1028 * u.nm, width=2*u.MHz, threshold_current=47*u.mA, max_current=250*u.mA,
                        dlambda_dA=0.015*u.nm/u.mA, voltage=1.3*u.V, dlambda_dT=0.12*u.nm/u.deg_C,
                        dP_dI=.18*u.mW/u.mA, tec_current=1.2*u.A))
    s_1270 = lp.add(LaserDiode("LD1270",1270 * u.nm, width=2*u.MHz, threshold_current=8*u.mA, max_current=70*u.mA,
                        dlambda_dA=0.003*u.nm/u.mA, voltage=1.7*u.V, dlambda_dT=0.08*u.nm/u.deg_C,
                        dP_dI=.166*u.mW/u.mA, tec_current=1*u.A))
    s_1430_yj = lp.add(LaserDiode("LD1430_yj", 1430 * u.nm, width=2*u.MHz, threshold_current=8*u.mA, max_current=70*u.mA,
                  dlambda_dA=0.003*u.nm/u.mA, voltage=1.7*u.V, dlambda_dT=0.08*u.nm/u.deg_C,
                  dP_dI=.166*u.mW/u.mA, tec_current=1*u.A))
    s_1430_hk = lp.add(LaserDiode("LD1430_hk", 1430 * u.nm, width=2*u.MHz, threshold_current=8*u.mA, max_current=70*u.mA,
                  dlambda_dA=0.003*u.nm/u.mA, voltage=1.7*u.V, dlambda_dT=0.08*u.nm/u.deg_C,
                  dP_dI=.166*u.mW/u.mA, tec_current=1*u.A))
    s_1510 = lp.add(LaserDiode("LD1510", 1510 * u.nm, width=0.5*u.MHz, threshold_current=8*u.mA, max_current=70*u.mA,
                        dlambda_dA=0.003*u.nm/u.mA, voltage=1.7*u.V, dlambda_dT=0.08*u.nm/u.deg_C,
                        dP_dI=.166*u.mW/u.mA, tec_current=1*u.A))
    s_2330 = lp.add(LaserDiode("LD2330", 2330 * u.nm, width=2*u.MHz, threshold_current=25*u.mA,
                        dlambda_dA=0.015*u.nm/u.mA, voltage=1.65*u.V, dlambda_dT=0.12*u.nm/u.deg_C,
                        dP_dI=.031*u.mW/u.mA, max_current=120*u.mA, tec_current=1.2*u.A))


    # Detectors
    atc_imager = lp.add(Imager("ATC", qe=TransmissionCurve.constant(ATC_QE)))
    pd_yj = lp.add(Photodiode("pd_yj", resp_wavelength_nm=FEMTO_QE_TC[0], resp_values=FEMTO_QE_TC[1],
                              noise=7.5 * u.femtowatt / u.Hz ** 0.5,
                              gain= 1e11 * u.V/u.A/2,
                              saturation=110 * u.picowatt
                              ))
    pd_hk = lp.add(Photodiode("pd_hk", resp_wavelength_nm=THOR_QE_TC[0], resp_values=THOR_QE_TC[1],
                              noise=2.11 * u.picowatt / u.Hz ** 0.5,
                              gain=4750*u.kV/u.A/2,
                              saturation=1.706 * u.microwatt, saturation_wavelength=2330 * u.nm
                              # technically saturation will happen about 20 mV sooner because of the bias offset
                              ))

    bspec = lp.add(Spectrograph("BSPEC", ECHELLE_ORDERS_FILE['yj'], ECHELLE_RESOLUTION_FILE['yj'],
                                qe=TransmissionCurve.constant(BSPEC_QE)))
    rspec = lp.add(Spectrograph("RSPEC", ECHELLE_ORDERS_FILE['hk'], ECHELLE_RESOLUTION_FILE['hk'],
                                qe=TransmissionCurve.constant(RSPEC_QE)))

    #Attenuators
    att_1028 = lp.add(VariableAttenuator("att_1028"))
    att_1270 = lp.add(VariableAttenuator("att_1270"))
    att_1430_yj = lp.add(VariableAttenuator("att_1430_yj"))
    att_1430_hk = lp.add(VariableAttenuator("att_1430_hk"))
    att_1510 = lp.add(VariableAttenuator("att_1510"))
    att_2330 = lp.add(VariableAttenuator("att_2330"))

    # Common filters, beams, and dichroics
    beam_ao = lp.add(OpticalBeam("beam_ao", n_inputs=2))
    ao_losses = lp.add(Filter("ao_losses"))
    beam_fei_in = lp.add(OpticalBeam("beam_fei_in", n_inputs=3))
    fei_pre_losses = lp.add(Filter("fei_pre_losses"))

    # ATC selector (J/H/JH/JHgap) as SelectableDichroic with modeled bandpasses
    atc_selector = lp.add(SelectableDichroic("atc_dichroic_selector", models=ATC_DICHROIC_MODELS, default="J"))

    # Channel‑splitting dichroic (CSD)
    csd = lp.add(Dichroic("csd", curves=CSD_DICHROIC_CURVES))

    # Common links

    # FEI input beam → ATC selector A_in
    lp.link(beam_ao.out, ao_losses.A_in)
    lp.link(ao_losses.B_out, beam_fei_in.inputs[0])
    lp.link(beam_fei_in.out, fei_pre_losses.A_in)
    lp.link(fei_pre_losses.B_out, atc_selector.A_in)

    # ATC selector → ATC imager (B_out) and → CSD (C_out)
    lp.link(atc_selector.B_out, atc_imager.in_p)
    lp.link(atc_selector.C_out, csd.A_in)

    # CSD feedback A_out → ATC selector C_in
    lp.link(csd.A_out, atc_selector.C_in)

    # -----------------
    # --- YJ branch ---
    # -----------------

    # WDM for YJ branch (3 inputs → 1 output)
    wdm_yj = lp.add(WavelengthDivisionMultiplexer("wdm_yj", n_inputs=3,
                                                  per_input=[TransmissionCurve.constant(1),
                                                             TransmissionCurve.constant(1),
                                                             TransmissionCurve.constant(1)]))

    # Retro switch (YJ): 1‑in → 2‑out
    sw_retro_yj = lp.add(Switch.one_to_many("sw21_yj_retro", common="C", choices=["A", "B"], default_choice="A"))

    # FEI feed switch: 1→2
    sw_fei_yj = lp.add(Switch.one_to_many("sw25_yj_fei", common="C", choices=["A", "B"], default_choice="A"))

    # PD branch: 2→1
    sw_pd_yj = lp.add(Switch.many_to_one("sw27_yj_pd", common="C", choices=["A", "B"], default_choice="A"))

    # Fibers
    f_yj_retro = lp.add(Fiber("fib_yj_retro"))
    f_yj_ao = lp.add(Fiber("fib_yj_ao"))
    f_yj_fei = lp.add(Fiber("fib_yj_fei"))

    # Science branch fiber, coupling handled by PIAA Selector
    f_yj_science = lp.add(Fiber("fib_yj_science"))

    # Photodiode branch fibers yj
    fib_yj_mmf_pd = lp.add(Fiber("fib_yj_mmf_pd"))
    # Coupling handled by PD Selector
    fib_yj_smf_pd = lp.add(Fiber("fib_yj_smf_pd"))

    # PIAA selector (SelectableFilter) with modes: high/low/vortex/clear (unity placeholders)
    piaa_sel_yj = lp.add(SelectableFilter("selector_yj_piaa", default="clear", models={
        "piaa": PIAA_TC_BIDIR,
        "vortex": VORTEX_TC_BIDIR,

        "vortex_dark": VORTEX_DARK_TC_BIDIR,
        "clear": NORMAL_FREESPACE_TC_BIDIR,
    }))

    # Focus selector (generic) with internal retro gating
    focus_sel_yj = lp.add(FocusSelector("selector_yj_focus", default="SMF"))


    # ---- Wiring per connectivity ----
    # Sources → Att → WDM
    f_1028 = lp.add(Fiber("jumper_1028"))
    lp.link(s_1028.out, f_1028.in_p)
    lp.link(f_1028.out_p, att_1028.in_p)
    lp.link(att_1028.out_p, wdm_yj.inputs[0])

    f_1270 = lp.add(Fiber("jumper_1270"))
    lp.link(s_1270.out, f_1270.in_p)
    lp.link(f_1270.out_p, att_1270.in_p)
    lp.link(att_1270.out_p, wdm_yj.inputs[1])

    f_1430_yj = lp.add(Fiber("jumper_1430_yj"))
    lp.link(s_1430_yj.out, f_1430_yj.in_p)
    lp.link(f_1430_yj.out_p, att_1430_yj.in_p)
    lp.link(att_1430_yj.out_p, sw_retro_yj.port("C_in"))  # C_in

    # Retro switch fanout
    lp.link(sw_retro_yj.port("A_out"), wdm_yj.inputs[2])  # C→A feeds WDM
    lp.link(sw_retro_yj.port("B_out"), f_yj_retro.in_p)  # C→B to retro fiber

    # WDM.out → FEI feed switch
    lp.link(wdm_yj.out, sw_fei_yj.port("C_in"))

    # FEI feed → AO / FEI fibers → FEI input beam
    lp.link(sw_fei_yj.port("A_out"), f_yj_ao.in_p)
    lp.link(sw_fei_yj.port("B_out"), f_yj_fei.in_p)
    lp.link(f_yj_ao.out_p, beam_ao.inputs[0])
    lp.link(f_yj_fei.out_p, beam_fei_in.inputs[1])

    # CSD B_out → PIAA.A_in → PIAA.B_out → Focus.IN_in
    lp.link(csd.B_out, piaa_sel_yj.A_in)
    lp.link(piaa_sel_yj.B_out, focus_sel_yj.IN_in)

    # Retro fiber → Focus.RETRO_in → Focus.IN_out → PIAA.B_in; PIAA.A_out → CSD.B_in (reverse; gating inside Focus)
    lp.link(f_yj_retro.out_p, focus_sel_yj.RETRO_in)
    lp.link(focus_sel_yj.IN_out, piaa_sel_yj.B_in)
    lp.link(piaa_sel_yj.A_out, csd.B_in)

    # Focus forward outputs → fibers
    lp.link(focus_sel_yj.MMF_out, fib_yj_mmf_pd.in_p)
    lp.link(focus_sel_yj.SMF_out, fib_yj_smf_pd.in_p)
    lp.link(focus_sel_yj.SCI_out, f_yj_science.in_p)

    # PD fibers to PD switch → PD
    lp.link(fib_yj_mmf_pd.out_p, sw_pd_yj.port("B_in"))  # B_in
    lp.link(fib_yj_smf_pd.out_p, sw_pd_yj.port("A_in"))  # A_in
    lp.link(sw_pd_yj.port("C_out"), pd_yj.in_p)

    # Science fiber → BSPEC
    lp.link(f_yj_science.out_p, bspec.in_p)

    # -----------------
    # --- HK branch ---
    # -----------------

    # WDM for HK branch (3 inputs → 1 output)
    wdm_hk = lp.add(WavelengthDivisionMultiplexer("wdm_hk", n_inputs=3,
                                                  per_input=[TransmissionCurve.constant(1),
                                                             TransmissionCurve.constant(1),
                                                             TransmissionCurve.constant(1)]))

    # Retro switch (HK): 1‑in → 2‑out
    sw_retro_hk = lp.add(Switch.one_to_many("sw22_hk_retro", common="C", choices=["A", "B"], default_choice="A"))

    # FEI feed switch: 1→2
    sw_fei_hk = lp.add(Switch.one_to_many("sw26_hk_fei", common="C", choices=["A", "B"], default_choice="A"))

    # PD branch: 2→1
    sw_pd_hk = lp.add(Switch.many_to_one("sw28_hk_pd", common="C", choices=["A", "B"], default_choice="A"))

    # Fibers
    f_hk_retro = lp.add(Fiber("fib_hk_retro"))
    f_hk_ao = lp.add(Fiber("fib_hk_ao"))
    f_hk_fei = lp.add(Fiber("fib_hk_fei"))

    # Science branch fiber, coupling handled by PIAA Selector
    f_hk_science = lp.add(Fiber("fib_hk_science"))

    # Photodiode branch fibers yj
    f_hk_mmf_pd = lp.add(Fiber("fib_hk_mmf_pd"))
    # Coupling handled by PD Selector
    f_hk_smf_pd = lp.add(Fiber("fib_hk_smf_pd"))

    # PIAA selector (SelectableFilter) with modes: high/low/vortex/clear
    piaa_sel_hk = lp.add(SelectableFilter("selector_hk_piaa", default="clear", models={
        "piaa": PIAA_TC_BIDIR,
        "vortex": VORTEX_TC_BIDIR,
        "vortex_dark": VORTEX_DARK_TC_BIDIR,
        "clear": NORMAL_FREESPACE_TC_BIDIR,
    }))

    # HK Focus selector (generic) with internal retro gating
    focus_sel_hk = lp.add(FocusSelector("selector_hk_focus", default="SMF"))

    # HK links
    f_1510 = lp.add(Fiber("jumper_1510"))
    lp.link(s_1510.out, f_1510.in_p)
    lp.link(f_1510.out_p, att_1510.in_p)
    lp.link(att_1510.out_p, wdm_hk.inputs[0])

    f_2330 = lp.add(Fiber("jumper_2330"))
    lp.link(s_2330.out, f_2330.in_p)
    lp.link(f_2330.out_p, att_2330.in_p)
    lp.link(att_2330.out_p, wdm_hk.inputs[1])

    f_1430_hk = lp.add(Fiber("jumper_1430_hk"))
    lp.link(s_1430_hk.out, f_1430_hk.in_p)
    lp.link(f_1430_hk.out_p, att_1430_hk.in_p)
    lp.link(att_1430_hk.out_p, sw_retro_hk.port("C_in"))  # C_in

    # Retro switch fanout
    lp.link(sw_retro_hk.port("A_out"), wdm_hk.inputs[2])  # C→A feeds WDM
    lp.link(sw_retro_hk.port("B_out"), f_hk_retro.in_p)  # C→B to retro fiber

    # WDM.out → FEI feed switch
    lp.link(wdm_hk.out, sw_fei_hk.port("C_in"))

    # FEI feed → AO / FEI fibers → FEI input beam
    lp.link(sw_fei_hk.port("A_out"), f_hk_ao.in_p)
    lp.link(sw_fei_hk.port("B_out"), f_hk_fei.in_p)
    lp.link(f_hk_ao.out_p, beam_ao.inputs[1])
    lp.link(f_hk_fei.out_p, beam_fei_in.inputs[2])

    # Wiring HK per map: CSD.C_out → PIAA_HK.A_in → PIAA_HK.B_out → Focus_HK.IN_in
    lp.link(csd.C_out, piaa_sel_hk.A_in)
    lp.link(piaa_sel_hk.B_out, focus_sel_hk.IN_in)

    # Retro HK: retro fiber → Focus_HK.RETRO_in → Focus_HK.IN_out → PIAA_HK.B_in; PIAA_HK.A_out → CSD.C_in
    lp.link(f_hk_retro.out_p, focus_sel_hk.RETRO_in)
    lp.link(focus_sel_hk.IN_out, piaa_sel_hk.B_in)
    lp.link(piaa_sel_hk.A_out, csd.C_in)

    # Focus_HK forward outputs → fibers
    lp.link(focus_sel_hk.MMF_out, f_hk_mmf_pd.in_p)
    lp.link(focus_sel_hk.SMF_out, f_hk_smf_pd.in_p)
    lp.link(focus_sel_hk.SCI_out, f_hk_science.in_p)

    # HK PD fibers to PD switch → PD
    lp.link(f_hk_mmf_pd.out_p, sw_pd_hk.pairs["B"][0])
    lp.link(f_hk_smf_pd.out_p, sw_pd_hk.pairs["A"][0])
    lp.link(sw_pd_hk.port("C_out"), pd_hk.in_p)

    # HK Science fiber → RSPEC
    lp.link(f_hk_science.out_p, rspec.in_p)

    # Defaults
    sw_retro_yj.set_state("C", "A")  # feed WDM by default
    sw_fei_yj.set_state("C", "A")  # toward AO path by default
    sw_pd_yj.set_state("A", "C")  # YJ PD reads SMF by default
    sw_retro_hk.set_state("C", "A")  # feed WDM by default
    sw_fei_hk.set_state("C", "A")  # toward AO path by default
    sw_pd_hk.set_state("A", "C")  # HK PD reads SMF by default
    focus_sel_yj.set_state("SMF")  # allow retro by default (YJ)
    focus_sel_hk.set_state("SMF")  # allow retro by default (HK)
    return lp
