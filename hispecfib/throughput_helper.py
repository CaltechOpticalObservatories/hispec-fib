
"""
throughput_helper.py

Two small APIs to compute net transmission curves from a HISPEC-style
throughput spreadsheet:

    - section_transmissions(path_to_excel) -> dict[str, (wl, T)]
    - range_transmissions(path_to_excel, rows) -> (wl, T)

Design goals:
- Keep dependencies light (numpy, pandas, scipy).
- Do not instantiate Lightpath graph objects for each row; compute on demand.
- Be tolerant of minor column/header variations in both the Excel and the
  referenced curve files.

Expected Excel schema (flexible, best-effort parsing):
- "Include?" (1 / 0 or True / False)
- "Type" in {"Note", "Coating", "Constant", "Internal Transmission"}
- "Name" (free text; "Note" rows delimit sections)
- "File" (for Coating or Internal Transmission; relative to the Excel file unless absolute)
- "Value" (float; for Constant it's the scalar; for Internal Transmission it's the length)
  The original teammate's logic for internal transmission:
      thickness_ratio = value / final_column_in_curve_file
      transmission = transmission_column ** thickness_ratio

Curve file formats supported (autodetected):
- CSV/TSV/space-delimited text with headers OR no headers.
- Identifies wavelength and transmission columns heuristically by column names
  (e.g., ['wavelength','lambda','wl'] and ['T','trans','throughput']) or
  falls back to the first two numeric columns.
- A reference-length column is optionally detected by name
  (['length','thickness','mm','cm','m','ref_len','L0']) or, if absent,
  by treating the last numeric column as a scalar reference (using its last value).

All wavelengths are returned exactly as present in the source curves (no unit changes).
Interpolation is linear; out-of-range fill is 1.0 (neutral element for multiplication).

Author: generated for HISPEC project (Python 3.12 compatible) using GPT5 by jib
"""

from __future__ import annotations

from _ast import Raise
from pathlib import Path
from typing import Dict, List, Tuple, Iterable, Union, Optional

import os
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d

RowIndex = Union[int, Iterable[int]]
WlArray = np.ndarray
TArray = np.ndarray

# -------------- Utilities --------------

def _coerce_bool(x) -> bool:
    if isinstance(x, (bool, np.bool_)): 
        return bool(x)
    try:
        if isinstance(x, (int, float, np.integer, np.floating)):
            return bool(int(x))
        s = str(x).strip().lower()
        if s in {"1","true","y","yes"}: return True
        if s in {"0","false","n","no",""}: return False
    except Exception:
        pass
    return False

def _first_sheet(path: Path) -> pd.DataFrame:
    xls = pd.ExcelFile(path)
    sheet = xls.sheet_names[0]
    df = pd.read_excel(path, sheet_name=sheet)
    return df

def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    # Lowercase, strip, simplify common names
    mapping = {}
    for c in df.columns:
        lc = str(c).strip().lower()
        mapping[c] = lc
    ndf = df.rename(columns=mapping)
    return ndf

def _find_col(ndf: pd.DataFrame, candidates: list[str], default: Optional[str]=None) -> Optional[str]:
    cols = list(ndf.columns)
    for cand in candidates:
        if cand in cols:
            return cand
    return default

def _resolve_curve_path(excel_path: Path, curve_file: str, path_to_data: Optional[str] = None) -> Path:

    # normalize separators cross-platform
    norm_str = str(curve_file).replace("\\", os.sep).replace("/", os.sep)
    if norm_str.startswith(os.sep):
        norm_str = norm_str[1:] #accidentally starts with /
    p = Path(norm_str)

    dir = Path(path_to_data) if path_to_data is not None else excel_path.parent / 'inputs'

    return dir / p

def _detect_numeric_columns(df: pd.DataFrame) -> list[str]:
    num_cols = []
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s):
            if not np.isnan(s).all():
                num_cols.append(c)
        else:
            # Try coercion
            try:
                pd.to_numeric(s.dropna().head(4))
                num_cols.append(c)
            except Exception:
                pass
    return num_cols

def _load_curve_file(path: Path) -> tuple[WlArray, TArray, Optional[float]]:
    """
    Returns (wavelength, transmission, reference_length or None)

    Heuristics:
    - Try to read with header autodetect (pandas.read_csv) and sep=None (python engine).
    - If that fails, try whitespace.
    - Identify wavelength & transmission columns by name; else first two numeric columns.
    - Identify reference length by name; else use last numeric column's LAST value
      if it's not one of the selected wl/T columns (or even if it is, but scalar).
    """
    # Try a few read strategies
    read_kwargs = [
        dict(sep=None, engine="python"),
        dict(sep=r"\s+", engine="python")
    ]
    last_err = None
    for kw in read_kwargs:
        try:
            df = pd.read_csv(path, comment="#", **kw)
            break
        except Exception as e:
            last_err = e
            df = None
    if df is None:
        raise RuntimeError(f"Unable to read curve file: {path} ({last_err})")

    # Clean column names
    cols_map = {c: str(c).strip().lower() for c in df.columns}
    df = df.rename(columns=cols_map)

    # If it's one unnamed column with delimited values, try splitting
    if df.shape[1] == 1:
        # Attempt to split on whitespace
        s = df.iloc[:,0].astype(str).str.strip()
        parts = s.str.split(r"\s+", expand=True)
        # Coerce numeric
        for i in range(min(3, parts.shape[1])):
            parts[i] = pd.to_numeric(parts[i], errors="coerce")
        df = parts
        df.columns = [f"col{i}" for i in range(df.shape[1])]

    num_cols = _detect_numeric_columns(df)
    if len(num_cols) < 2:
        raise ValueError(f"Curve file {path} must contain at least two numeric columns (found {len(num_cols)}).")

    wl_col, t_col = num_cols[:2]

    L0_col = num_cols[-1] if len(num_cols) > 2 else None

    wl = pd.to_numeric(df[wl_col], errors="coerce").to_numpy(dtype=float)
    T  = pd.to_numeric(df[t_col],  errors="coerce").to_numpy(dtype=float)

    # Clean NaNs and monotonic x
    mask = np.isfinite(wl) & np.isfinite(T)
    wl, T = wl[mask], T[mask]
    order = np.argsort(wl)
    wl, T = wl[order], T[order]
    T = T/100 if T.max() > 1.05 else T
    wl = wl*1000 if wl[0] < 100 else wl

    # Reference length detection:
    L0 = None
    if L0_col is not None:
        L0 = pd.to_numeric(df[L0_col], errors="coerce").dropna().to_numpy(dtype=float)[order]

    return wl, T, L0

def _multiply_curves(curves: list[tuple[WlArray, TArray]|float] | dict[str,list[tuple[WlArray, TArray]|float]]) -> tuple[WlArray, TArray] | tuple[None, TArray]:
    """
    Given a list of (wl, T) curves (or a dict of the same, interpolate onto a common wavelength grid
    and multiply. If dict do for each key, then return a dict of common wavelengths and multiplied curves.

    Strategy:
    - Determine overlapping wavelength range across all curves.
    - Create a master grid of 2000 points across the overlap.
    - Interpolate curves with linear interp; out-of-range fill = 1.0.
    """
    if not curves:
        raise ValueError("No curves to multiply.")

    if isinstance(curves, dict):
       return {k: _multiply_curves(curves[k]) for k in curves.keys()}

    # Compute overlap
    mins = [c[0][0] for c in curves if isinstance(c, tuple)]
    maxs = [c[0][-1] for c in curves if isinstance(c, tuple)]
    if not mins:
        return None, np.prod(curves, dtype=float)

    wl_min = np.nanmin(mins)
    wl_max = np.nanmax(maxs)
    # if not np.isfinite(wl_min) or not np.isfinite(wl_max) or wl_max <= wl_min:
    #     # Fall back to a union grid if overlap is empty
    #     merged = np.unique(np.concatenate([c[0] for c in curves]))
    #     wl_grid = merged
    # else:
    # dense grid in overlap
    wl_grid = np.linspace(wl_min, wl_max, int((wl_max - wl_min)*2))

    T_total = np.ones_like(wl_grid, dtype=float)
    for c in curves:
        if isinstance(c, tuple):
            wl, T = c
            f = interp1d(wl, T, kind="linear", bounds_error=False, fill_value='extrapolate', assume_sorted=True)
            T_total *= f(wl_grid).clip(0, 1)
        else:
            T_total *= c

    return wl_grid, T_total


def _process_curve_file(curve_path, length_value:float|None = None) -> tuple[WlArray, TArray]:
    wl, T, L0 = _load_curve_file(curve_path)

    if length_value is not None:
        # Apply thickness scaling if possible
        ratio = length_value / L0
        # clip negative/NaN defensively
        ratio[~np.isfinite(ratio)] = 1.0
        T = np.power(T, ratio)

    return wl, T


def _rows_to_curves(excel_path: Path, ndf: pd.DataFrame, row_indices: Iterable[int],
                    path_to_data: Optional[str] = None, force_include:bool = False,
                    exclude: Optional[list[str]] = None, all_modes: bool = False,
                    only_named: Optional[list[str]]=None) -> list[tuple[WlArray, TArray]]:
    """
    Convert selected rows to curves, respecting Include? and Type.
    """
    include_col = _find_col(ndf, ["include?","include","inc"])
    type_col    = _find_col(ndf, ["type","kind","category"])
    name_col    = _find_col(ndf, ["name","component","label","element"])
    file_col    = _find_col(ndf, ["file","path","curve","transmission file","transmission_file", 'datafile'])
    value_col   = _find_col(ndf, ["value","val","length","thickness"])
    modes_col   = _find_col(ndf, ["modes","mode"])

    only_named = only_named or []

    curves: list[tuple[WlArray, TArray]] = []

    modal_data: dict[str, list[tuple[WlArray, TArray]]] = {}

    for ridx in row_indices:
        if ridx < 0 or ridx >= len(ndf):
            continue
        row = ndf.iloc[ridx]

        # Respect Include? if present; default to include
        if include_col is not None:
            if not force_include and not _coerce_bool(row[include_col]):
                continue

        rtype = str(row[type_col]).strip().lower() if type_col is not None else ""

        skip = False
        for e in exclude or []:
            if e in str(row[name_col]).strip().lower():
                skip = True
                print(f"Excluding row {ridx} due to '{e}' in Name {str(row[name_col]).strip().lower()}.")
                break

        if only_named and str(row[name_col]).strip() not in only_named:
            skip = True

        if skip:
            continue

        if rtype == "note":
            # Delimiter only; skip
            continue

        if rtype in {"coating","internal transmission","internal_transmission","internaltransmission"}:
            curve_path = None
            if file_col is not None and not (pd.isna(row[file_col]) or str(row[file_col]).strip()==""):

                length_value = None
                if "internal" in rtype:
                    length_value = float(row[value_col])

                default_file = str(row[file_col]).strip()
                modes = [m.strip() for m in str(row[modes_col]).split(',')]
                default_modes = [m for m in modes if m in default_file]
                if all_modes and len(default_modes)==1:
                    for mode in modes:
                        mode_file = default_file.replace(default_modes[0], mode)

                        curve_path = _resolve_curve_path(excel_path, mode_file, path_to_data=path_to_data)
                        if curve_path is None:
                            # If no file, skip this row
                            raise ValueError(f"Row {ridx} must have a 'File' column entry.")

                        wl, T = _process_curve_file(curve_path, length_value=length_value)
                        if mode not in modal_data:
                            modal_data[mode] = [(wl, T)]
                        else:
                            modal_data[mode].append((wl, T))

                else:
                    curve_path = _resolve_curve_path(excel_path, default_file, path_to_data=path_to_data)
                    if curve_path is None:
                        raise ValueError(f"Row {ridx} must have a 'File' column entry.")
                    wl, T = _process_curve_file(curve_path, length_value=length_value)
                    curves.append((wl, T))

            continue

        if rtype == "constant":
            # Multiply a scalar across wavelength grid.
            if value_col is not None and pd.notna(row[value_col]):
                const_val = float(row[value_col])
            else:
                raise ValueError(f"Constant row {ridx} must have a 'Value' column.")

            curves.append(const_val)
            continue

        # Unknown type
        raise ValueError(f"Row {ridx} has an unknown 'Type' value: {rtype}.")

    if modal_data:
        for mode in modal_data:
            modal_data[mode].extend(curves)
        return modal_data
    else:
        return curves

# -------------- Public API --------------

def section_transmissions(path_to_excel: Union[str, Path], include_sections:Optional[Union[list[str]|str]]=None,
                          names: Optional[Union[list[str]|str]]=None,
                          path_to_data: Optional[Union[str, Path]]=None, force_include:bool=False,
                          exclude:Optional[Union[list[str], str]] = None, all_modes:bool=False,
                          ) -> Dict[str, tuple[WlArray, TArray]]|tuple[WlArray, TArray]:
    """
    Compute net transmission per section defined by 'Note' rows.
    Returns a dict: {section_name: (wavelength_array, transmission_array)}.

    A section is the span of rows between successive "Note" rows. The name of
    the section is taken from the "Name" (or similar) column of the "Note" row.
    Rows must also be marked as included ("Include?" == 1/True) to contribute.
    """
    excel_path = Path(path_to_excel)
    df_raw = _first_sheet(excel_path)
    ndf = _normalize_columns(df_raw)

    include_col = _find_col(ndf, ["include?","include","inc"])
    type_col    = _find_col(ndf, ["type","kind","category"])
    name_col    = _find_col(ndf, ["name","component","label", "element"])

    if type_col is None:
        raise ValueError("Excel sheet must have a 'Type' column (or close equivalent).")

    # Identify note rows & section boundaries
    note_rows = []
    for i, v in enumerate(ndf[type_col].astype(str).str.strip().str.lower().tolist()):
        if v == "note":
            note_rows.append(i)

    # Add an implicit sentinel end
    indices = note_rows + [len(ndf)]

    names = [names] if isinstance(names, str) else names or []

    exclude = [exclude] if isinstance(exclude, str) else exclude or []
    exclude = [e.lower() for e in exclude]

    include_sections = [include_sections] if isinstance(include_sections, str) else include_sections or []

    sections: Dict[str, tuple[WlArray, TArray]] = {}

    for j in range(len(indices)-1):
        note_idx = indices[j]
        start = note_idx + 1
        end   = indices[j+1]
        section_name = f"Section {j+1}"
        if name_col is not None:
            nm = str(ndf.iloc[note_idx][name_col])
            if nm and nm.strip():
                section_name = nm.strip()

        if include_sections and section_name not in include_sections:
            continue

        # Gather curves inside [start, end)
        curves = _rows_to_curves(excel_path, ndf, range(start, end), exclude=exclude, path_to_data=path_to_data,
                                 all_modes=all_modes, force_include=force_include, only_named=names)
        if not curves:
            continue

        sections[section_name] = _multiply_curves(curves)

    if len(sections) == 1:
        return sections[list(sections.keys())[0]]

    return sections

def range_transmissions(path_to_excel: Union[str, Path], rows: RowIndex) -> tuple[WlArray, TArray]:
    """
    Compute net transmission for an arbitrary selection of rows.

    Parameters
    ----------
    path_to_excel : str | Path
        Path to the Excel workbook (first sheet is used).
    rows : int or Iterable[int]
        Row number(s) using *zero-based* DataFrame indexing of the first sheet.
        Noncontiguous rows are allowed.

    Returns
    -------
    (wl, T) : tuple of numpy arrays
        The common wavelength grid and the net transmission (product of all
        included rows after interpolation/scaling).
    """
    excel_path = Path(path_to_excel)
    df_raw = _first_sheet(excel_path)
    ndf = _normalize_columns(df_raw)

    if isinstance(rows, (int, np.integer)):
        row_indices = [int(rows)]
    else:
        row_indices = [int(r) for r in rows]

    curves = _rows_to_curves(excel_path, ndf, row_indices)
    if not curves:
        raise ValueError("No included/valid rows found in the specified range.")
    return _multiply_curves(curves)


def make_common_grid(curves:list[tuple[WlArray, TArray]], grid:Optional[WlArray]=None) -> list[tuple[WlArray, TArray]]:
    all_curves = [c for c in curves if isinstance(c, tuple)]
    all_curves.extend([v for c in curves if isinstance(c, dict) for v in c.values()])

    # Compute overlap
    if grid is None:
        mins = [c[0][0] for c in all_curves if isinstance(c, tuple)]
        maxs = [c[0][-1] for c in all_curves if isinstance(c, tuple)]

        wl_min = np.nanmin(mins)
        wl_max = np.nanmax(maxs)
        wl_grid = np.linspace(wl_min, wl_max, int((wl_max - wl_min)*2))
    else:
        wl_grid = grid

    out = []

    for c in curves:
        if isinstance(c, dict):
            out.append({})
            for k in c:
                d = c[k]
                f = interp1d(*d, kind="linear", bounds_error=False, fill_value='extrapolate', assume_sorted=True)
                out[-1][k] = wl_grid, f(wl_grid).clip(0, 1)
        else:
            f = interp1d(*c, kind="linear", bounds_error=False, fill_value='extrapolate', assume_sorted=True)
            out.append((wl_grid, f(wl_grid).clip(0, 1)))

    return out