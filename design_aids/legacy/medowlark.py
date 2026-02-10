import numpy as np
import os

class MedowlarkData:
    """
    MedowlarkData class for parsing a Medowlark polarimeter savefile into a numpy recarray.

    ML_FILE_DTYPE: np.dtype
         Data type definition for the parsed data.
         The file format is tab-delimited, with a header row:
         # Timestamp	S0	S1	S2	S3	DOP	DOLP	DOCP	Phase	e	eta	Temperature
         # 0:0:0.032	0.890	0.280	-0.966	0.009	1.006	1.006	0.009	-0.510	0.004	-36.915	33.548

    __init__(self, file: str)
        Parse a Medowlark polarimeter savefile into a numpy recarray.

        Args:
            file: a file path

    s(self) -> np.ndarray
        S mode polarization, computed on the fly.

    p(self) -> np.ndarray
        P mode polarization, computed on the fly.
    """
    ML_FILE_DTYPE = np.dtype([('timestamp', 'U12'),
                              ('s0', np.float64),
                              ('s1', np.float64),
                              ('s2', np.float64),
                              ('s3', np.float64),
                              ('dop', np.float64),
                              ('dolp', np.float64),
                              ('docp', np.float64),
                              ('phase', np.float64),
                              ('e', np.float64),
                              ('eta', np.float64),
                              ('temperature', np.float64)])

    def __init__(self, file: str):
        """
        Parse a Medowlark polarimeter savefile into a numpy recarray
        Args:
            file: a file path
        """
        self.name = os.path.basename(file)
        self.file = file
        x = np.loadtxt(file, delimiter='\t', skiprows=2, dtype=type(self).ML_FILE_DTYPE)
        self.data = x.view(np.recarray)

    @property
    def s(self)->np.ndarray:
        """ S mode polarization, computed on the fly """
        return (self.data.s0+self.data.s1)/2

    @property
    def p(self)->np.ndarray:
        """ P mode polarization, computed on the fly. """
        return (self.data.s0-self.data.s1)/2


import blosc2, numpy as np
typical_flux = 1000
flux_std = 100
darkscatter_rate = 100
darkscatter_rate_std = 10
fraction_illuminated = 0.5
n_frames = 1000
frame_time = 2.38

ramp_fluctuation = 0.05

illuminated_slope = (typical_flux, flux_std)
dark_slope = (darkscatter_rate, darkscatter_rate_std)

slopes=np.zeros(int(4096*4096))
slopes[:int(np.ceil(4096*4096*fraction_illuminated))] = np.random.normal(*illuminated_slope, size=int(4096*4096*fraction_illuminated))
slopes[:int(np.ceil(4096*4096*fraction_illuminated))] = np.random.normal(*dark_slope, size=int(4096*4096*fraction_illuminated))

ramp_salt = np.random.normal(size=(slopes.size, n_frames))*ramp_fluctuation+1

ramp = ((slopes[..., None] * np.arange(n_frames)/frame_time)*ramp_salt).reshape(4096,4096, n_frames)


compressed_ramp = blosc2.pack_array(ramp)
print(f'Compressed {ramp.nbytes/1024**3:.1f} Gib to {len(compressed_ramp)/1024**3:.1f} GiB '
      f'(factor of {len(compressed_ramp)/ramp.nbytes:.1%})')