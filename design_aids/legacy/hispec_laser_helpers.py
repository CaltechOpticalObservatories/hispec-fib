import numpy as np
import astropy.units as u
import astropy.constants as c
import scipy.special
from scipy.interpolate import InterpolatedUnivariateSpline
from specutils import Spectrum1D
from synphot.models import GaussianFlux1D


class TIBCalDetection:
    def __init__(self, levels, photons, noise, saturation):
        self.levels = levels
        self.photons = photons
        self.noise = noise
        self.saturation = saturation
        self.snr = self.photons/np.sqrt(self.photons+self.noise**2)
        self.saturation_mask = self.photons > self.saturation

    def sn(self, saturated=np.nan, collapse=np.max):
        snr = self.snr.copy()
        snr[self.saturation_mask] = saturated
        if snr.ndim ==1:
            return snr
        if collapse ==np.sum:
            return np.sqrt(collapse(snr**2, axis=0))
        else:
            return collapse(snr, axis=0)

@dataclasse
class Flux:
    nominal_wavelength: float
    nominal_width: float
    flux: float|GaussianFlux1D

class Diode:
    def __init__(self, wavelength, width,
                 threshold_current,
                 max_current=300 * u.mA,
                 dP_dI=.15 * u.W / u.A,
                 dlambda_dT=0 * u.nm / u.deg_C,
                 dlambda_dA=0 * u.nm / u.A,
                 voltage=None,
                 current_step = 0.1*u.mA,
                 tec_current=None):
        """width in FWHM"""
        self.wavelength = wavelength
        if width.si.unit == u.Hz:
            width = (wavelength ** 2 / c.c * width).to('nm')
        self.width = width
        self.voltage = voltage
        self.threshold_current = threshold_current

        if dP_dI is None:  # use 1:1 current unit to photon
            self.dP_dI = c.h * c.c / self.wavelength / u.mA / u.s
        else:
            self.dP_dI = dP_dI
        self.dlambda_dT = dlambda_dT
        self.dlambda_dA = dlambda_dA
        self.max_current = max_current
        self.current_step = current_step

    @property
    def currents(self):
        return np.arange(self.threshold_current.to('mA').value, self.max_current.to('mA').value,
                         self.current_step.to('mA').value) * u.mA

    def flux(self, current:np.ndarray=None, spectrum=False, tput=1):
        if current is None:
            current = self.currents

        if spectrum:
            power = self.dP_dI * current * tput
            power[current > self.max_current] = 0
            power[current < self.threshold_current] = 0

            photons = (power*self.wavelength/c.h/c.c*1*u.s).decompose()
            amplitude = photons/self.width.to('AA')/(2*np.sqrt(2*np.log(2)))/np.sqrt(2*np.pi)*u.ph/u.s/u.cm**2
            return [Flux(self.wavelength, self.width, GaussianFlux1D(amplitude=a, mean=self.wavelength, fwhm=self.width)) for a in amplitude]
            # total_flux = (power/u.cm**2).to('erg/s/cm^2')
            # return [GaussianFlux1D(amplitude=amplitude, mean=self.wavelength, fwhm=self.width)*
            #         (1*u.cm**2*u.s) for tf in total_flux]
        else:
            ret = (self.dP_dI * current) / c.h / c.c * self.wavelength * tput
            ret[current > self.max_current] = 0
            ret[current < self.threshold_current] = 0
            return [Flux(self.wavelength, self.width, v) for v in ret.si]


class Spec:
    def __init__(self, name, orders, resolution, noise=6 * u.electron / u.pixel, trace_width=3, trunk_throughput=0.1,
                 saturation=100000):
        self.name = name
        self.orders = np.loadtxt(orders, delimiter=',',
                                 dtype=[('order', int), ('min_l', np.float64), ('max_l', np.float64)]).view(np.recarray)
        ## Order, Wavelength (nm), X Pos (mm), Y Pos (mm), Dispersion (nm/pix), FWHM (pix), Resolution
        self.res = np.loadtxt(resolution,
                              dtype=[('order', np.float64), ('l', np.float64), ('x', np.float64), ('y', np.float64),
                                     ('dispersion', np.float64), ('fwhm', np.float64),
                                     ('resolution', np.float64)]).view(np.recarray)
        self.noise = noise
        self.trace_width = trace_width
        self.trunk_throughput = trunk_throughput
        self.saturation = saturation

    def detect(self, fluence, texp=1 * u.s, sat=True):

        wavelength = fluence[0].nominal_wavelength
        print(wavelength, fluence[0].mean)
        fluence = [f.flux for f in fluence]

        found_in_order = (self.orders.min_l < wavelength / u.nm) & (wavelength / u.nm < self.orders.max_l)
        if not found_in_order.any():
            return TIBCalDetection(fluence, u.Quantity(np.zeros_like(fluence)),
                                   u.Quantity(np.zeros_like(fluence)), u.Quantity(np.zeros_like(fluence)))
        result = {}

        for order in self.orders[found_in_order]:
            # order = self.orders[in_order]
            in_res = self.res.order == order.order
            dispersion = self.res[in_res].dispersion.mean() * u.nm / u.pixel

            diode_pixels = np.ceil(fluence[0].stddev * 2.354 / dispersion)
            res_elem_pixels = np.ceil(fluence[0].mean / self.res[in_res].resolution.mean() / dispersion)

            trace_sigma = self.trace_width / 2 / np.sqrt(2) / scipy.special.erfinv(.98)
            net_pix_flux = scipy.special.erf((np.arange(self.trace_width / 2) + .5) / trace_sigma / np.sqrt(2))
            pix_frac = np.diff(net_pix_flux) / 2
            trace_flux_frac = np.concatenate((pix_frac[::-1], [net_pix_flux[0]], pix_frac))

            if diode_pixels<=res_elem_pixels:
                print(f'{wavelength} diode_pixels {diode_pixels} are unresolved in {order}')
                photons = u.Quantity([[(f.integrate()*texp).value for f in fluence]])

                fwhm = fluence[0].mean / self.res[in_res].resolution.mean() / dispersion
                sigma = fwhm / (2 * np.sqrt(2 * np.log(2)))

                net_pix_flux = scipy.special.erf((np.arange(res_elem_pixels.value / 2) + .5 )*u.pix / sigma / np.sqrt(2))
                pix_frac = np.diff(net_pix_flux) / 2
                spec_flux_frac = np.concatenate((pix_frac[::-1], [net_pix_flux[0]], pix_frac))

                photons = photons*spec_flux_frac[:,None]

            else:

                spectral_pixels = min(diode_pixels*3, 4096 * u.pix)
                _, l0, l1 = order
                min_l = max(l0*u.nm, fluence[0].mean-spectral_pixels*dispersion/2)
                max_l = min(l1*u.nm, fluence[0].mean+spectral_pixels*dispersion/2)
                wave_grid = np.arange(min_l.value, max_l.value+dispersion.value/2, dispersion.value)

                photons = u.Quantity([(texp * f(wave_grid*u.nm)  * dispersion).to("ph / (pix cm2)").value
                                      for f in fluence]).T  # wavelength, fluence

            photons = (photons*trace_flux_frac[:,None, None]).reshape(-1, photons.shape[-1])
            # noise = n_pixels * self.noise / u.electron
            #
            # print(f'Order {order.order}:\n'
            #       f' Got {photons.si.sum().value:.0g} phot\n'
            #       f' Noise {noise.sum().si.value:.2g}, saturation {self.saturation:.2g} \n '
            #       f' Npix={photons[:,:,0].size}')

            result[order.order] = TIBCalDetection(fluence, photons.si, self.noise / u.electron*u.pix, self.saturation)

        return result

class ATC:
    def __init__(self, noise=12 * u.electron / u.pixel, n_pixels=13, saturation=100000):
        self.name = 'atc'
        self.n_pixels = n_pixels
        self.noise = noise
        self.saturation = saturation

        fwhm = 2.7
        a = n_pixels/fwhm/2
        sigma = fwhm / (2*np.sqrt(2*np.log(2)))
        norm = fwhm**2*np.pi*scipy.special.erf(a/np.sqrt(2))**2/np.log(16)

        # make an array with the gaussian values in each pixel (flat)
        xy = np.sqrt((np.array(list(map(np.ravel, np.meshgrid(np.linspace(-n_pixels / 2, n_pixels / 2, num=n_pixels),
                                                              np.linspace(-n_pixels / 2, n_pixels / 2,
                                                                          num=n_pixels))))) ** 2).sum(0))
        self.spot = np.exp(-xy ** 2 / 2.0 / sigma ** 2) / norm

    def detect(self, fluence, texp=1 * u.s, sat=True):
        fluence = np.array([f.flux for f in fluence])
        photons = fluence * texp * self.spot[..., None]
        noise = self.noise * u.pix / u.electron
        return TIBCalDetection(fluence, photons.si, noise.si, self.saturation)

class Femto:
    def __init__(self, name, noise=7.5 * u.femtowatt / u.Hz ** 0.5, saturation=110 * u.picowatt,
                 adc_noise=0.6 * u.mV / (10 *u.V),
                 qe=None):
        """

        Args:
            name:
            noise:
            saturation:
            adc_noise: As fraction of full saturation range, e.g. 14 bit quantization noise of 0-10V would be about
            .6mV/10 or 6e-5 of the saturation, adds in quadrature with femto noise, set to 0 to turn off
        """
        self.name = name
        self.noise = noise
        self.saturation = saturation
        self.adc_noise = adc_noise
        self.qe = {} if qe is None else qe

    def detect(self, fluence, texp=1 * u.s, sat=True):
        """

        :param wavelength: wavelength in nm
        :param fluence: photon fluence
        :param texp: expt in s
        :return:
        """

        # noise = self.noise*u.Hz**0.5/c.h/c.c*source.wavelength*u.s
        # photons = u.Quantity([fei_flux*loss for cf, loss in fei_throughput.items()])
        #
        # photons_clipped = photons.copy()
        # # photons_clipped[photons>self.saturation*u.s/c.h/c.c*source.wavelength]=0
        # saturation = (self.saturation*u.s/c.h/c.c*source.wavelength)
        # photons_clipped = photons.clip(0,(self.saturation*u.s/c.h/c.c*source.wavelength))
        # sn = photons_clipped/np.sqrt(photons_clipped+noise**2)

        fluence = np.array([f.flux for f in fluence])
        wavelength = fluence[0].nominal_wavelength

        adc_noise = self.saturation * self.adc_noise
        qe = self.qe.get(int(wavelength.value), 1.0)
        photon_energy = c.h * c.c / wavelength
        noise = np.sqrt((self.noise * (1/texp) ** 0.5)**2 + adc_noise**2)
        phot_eq_noise = noise / photon_energy * u.s  #drop the per unit time as we've accounted above and are per measurement
        photons = qe * fluence * texp

        # energy = photons * photon_energy
        saturation = self.saturation * texp / photon_energy

        # energy[energy > saturation] = np.nan if sat else 0

        return TIBCalDetection(fluence, photons.si, phot_eq_noise.si, saturation.si)

