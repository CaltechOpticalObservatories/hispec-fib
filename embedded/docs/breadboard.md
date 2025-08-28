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
#### ADS1115 16bit ADC
- Needs Vcc=5 for 50Ohm PD termination
- PD on A0 & A1
- I2C addr: 0x48 (default) or 0x49 (ADDR tied to Vcc)
- Needs 2-channels of LL shifting
- Use I2C0 on pins GP4 (SDA) and GP5 (SCL)
- Kit board has 10K pullups, do we need to get rid of as have pullups on 3.3v side of LL translation?
- Requires 50 Ohm termination resistor on BNC to ADC. (10V -> 5V)
- Should clamp at Vdd+.3 (so lets say .2V above vcc with a shottkey(?) diode)?
- Needs to be set to +-6.144 V

#### Libraries
 - https://github.com/gavinlyonsrepo/ADS1x15_PICO
 - https://github.com/antgon/pico-ads1115
 - https://github.com/robert-hh/ads1x15
 - https://github.com/wollewald/ADS1115_mpy


### Variable Attenuation Control

#### DAC7578SPW 8chan DAC driving 3x OPA2991 2 channel OpAmp
- 0 - 4095 (Vref, default=Vcc)
- must not exceed max voltage of variable atten in use
- Kit board has 10K pullups, do we need to get rid of as have pullups on 3.3v side of LL translation?
- Use I2C1 on pins GP2 (SDA) and GP3 (SCL)
- Address (0x4C float, 0x48 GND, 0x4A VCC) (use 0x4c float, default)
- Use Vcc=3.3
- Use opamp gain to avoid LL shifting
- OpAmp OPA2991 with gain then supplies required current/voltage to attenuator.

Drives: 
- FVOA (resistive, typ~3.5V 80mA @ full atten)
- MSOA (resistive, typ~0.5-3.25V, DNE 4.5V, something like 24-38 mA, datasheet unclear)
- VOAM (capacitive unpol., 0-6V, improved drive with OPA uses )

Resistors @ 28k and 100k or 50k and 100k (VOAM)


#### Libraries
- https://github.com/adafruit/Adafruit_CircuitPython_DACx578
- https://github.com/adafruit/Adafruit_DACX578
- https://github.com/marcrickenbach/dac7578
- 
### Laser Diodes
- UART1 GP8 (TX) & GP9 (RX) 3.3v
- LL shifter

### Power on/off
- GP6 (check 120V relay for current draw of opto as unspecified)

### MEMS Switches

####  PCAL6416AHF,128 (I2C 16x GPIO expander) 
- 3.3V i2c
- 5V gpio
- 25mA max drive
- Address 0x20 or 0x21 (use 0x20 ADDR to GND)
- Use I2C1 on pins GP2 (SDA) and GP3 (SCL)
- Configure ase open drain for FFSW as they have 5V pullups
- Configure as push-pull for FFLS

##### Libraries
- https://github.com/BenjamimKrug/PCAL6416A
- https://github.com/SolderedElectronics/Inkplate-micropython/blob/master/PCAL6416A.py

#### SI3552DV
- N & P MOSFET
- 2x each for FFSW
- 2x 4.7k resistors for pullups

#### DMP3085LSD  
- 2x P  MOSFET
- 1x each for FFLS
- 1x 4.7k resistor for status line

# To Breadboard

### Solder up
- 4 SI3552DV
- 1 DMP3085LSD
- 1 PCAL6416AHF
- 3 OPA2991

### Pins to
- Pico
  - Use I2C1 on pins GP2 (SDA) and GP3 (SCL)  (gpio & dac w/o)
  - Use UART1 GP8 (TX) & GP9 (RX) 3.3v (w/ll)
  - Use I2C0 on pins GP4 (SDA) and GP5 (SCL) (adc w/ ll)
  - Power enable on pin GP6
- DAC
- ADC
- 2x LL shifter 

### Find
- 100k x6
- 28k x6
- 52k x6
- 5V & 3.3V supply
- 4.7k  x9

## Other 
- https://github.com/raspberrypi/FreeRTOS-Kernel