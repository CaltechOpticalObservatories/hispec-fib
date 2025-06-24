## Power:

Adafruit BFF 5-20Vin 5V@1.2A out

Level Shifting:

4bit level converters (phillips bidirectional design)

## Controller
[W5500-EVB-Pico2](https://docs.wiznet.io/Product/iEthernet/W5500/w5500-evb-pico2)

RP2350
W5500

https://github.com/micropython/micropython/tree/master/ports/rp2/boards/W5500_EVB_PICO
https://github.com/micropython/micropython/tree/master/ports/rp2/boards/RPI_PICO2


### Photodiode Monitoring
Device: ADS1115 16bit ADC

Requires 50 Ohm termination resistor on BNC to ADC. (10V -> 5V)

Should clamp at Vdd+.3 (so lets say .2V above vcc with a shottkey(?) diode)

#### Libraries
 - https://github.com/gavinlyonsrepo/ADS1x15_PICO
 - https://github.com/antgon/pico-ads1115
 - https://github.com/robert-hh/ads1x15
 - https://github.com/wollewald/ADS1115_mpy


### Variable Attenuation Control

Device: DAC7578SPW 8chan DAC driving 3x OPA2991 2 channel OpAmp

#### Libraries
- https://github.com/adafruit/Adafruit_CircuitPython_DACx578
- https://github.com/adafruit/Adafruit_DACX578


### MEMS Switches

Device PCAL6416AHF,128 (I2C 16x GPIO expander)

SI3552DV N & P MOSFET   2x each for FFSW
DMP3085LSD 2 P MOSFET   1x each for HHLS

#### Libraries
- https://github.com/BenjamimKrug/PCAL6416A
- https://github.com/SolderedElectronics/Inkplate-micropython/blob/master/PCAL6416A.py
