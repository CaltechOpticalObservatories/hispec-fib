### NH8 Initial setup
Make sure all DIP are off. This is a binary modbus address offset. With all off then modbus addresses will be 0x1 - 0x6 

### SF8025 Initial Setup

1. Remove the "Driver Short" jumper only *__after__* installing the laser diode.
2. Leave the DRIVER TEC DIP switches to off. This are for local manual control and we use software.
3. The current protection threshold level sets with DRV OC potentiometer. Get with software and set for each diode.
4. We want to disable the "External NTC" as it isn't part of the system

### Drivers, etc. 
If on windows you may need an FTDI serial driver. I'd suggest plugging in the NH8 first and seeing if windows just sorts it out. Mac/Linux come with drivers for it.
### Installing an environment
1. Clone [hispec-fib](git@github.com:CaltechOpticalObservatories/hispec-fib.git)main branch. 
2. Use envronment.yaml to create a working python environment. E.g. `mamba env create --file envirnoment.yaml --name <your env name here>`
3. activate environmnet
4. run the jupyter notebook 

## Electrical
#### Laser Diode Subsystem
- **_DO NOT EXCEED 5.1V!_**  
- The diode subsystem is 5VDC. 
- As of 20255.6.25 I've set it up to use channel two of the bench supply in the HISPEC lab. 
### Anticipated Static Attenuation Chains
- 1028: -90.0 to -73.0 dB, range 17.0 dB, **static -73.0 dB**
- 1270:  -70.0 to -40.0 dB, range 30.0 dB, **static -40.0 dB**
- 1430: range 0.0 dB, **static -100.0 dB**
- 1510: -80.0 to -33.0 dB, range 47.0 dB, **static -33.0 dB**
- 2330: -73.0 to -3.0 dB, range 70.0 dB, **static -3.0 dB**
#### Variable Attenuators
-  **_DO NOT EXCEED 4.2V!_** Limit the current to ~50mA
- The two variable attenuators are normally opaque and are resistive loads, I think 3.5VDC should be 0dB attenuation.
- ## Set attenuation by changing voltage in the 0-3.5V range.
- Datasheet suggest there may be some hysteresis depending on which direction the setpoint is approached. 
- #### FVOA
	- Do NOT Exceed 6VDC or 220mW.
	- Do not plan to test beyond 4V
	- Resistive load around 163 ohms. 3.5v @ 80mW (23mA) is typical for full transmission/attenuation of standard SM28 fiber
	- Response is ~loglinear in 1.87 - 3.25 V window 0-60dB/60dB-0.  
	- Up to 5.5V @ core diam of 62.5 um (which we don't use in HISPEC TIB). 
- #### MSOA
	- Do NOT Exceed 4.5VDC. 
	- Operation appears similar 0-70dB over 0.5-3.25V
	- Datasheet advises 70 Ohm resistor implying 65mA drive current, suggest internal resistance may be ~119 ohm (170mW @ 4.5V w/o ext resistor).
	- Expect a full open/closed drive current of between 24 - 38 mA
### Basics
The sample notebook enumerates the core laser driver limits and data sheets for the diodes are in [TIB Datasheets](https://caltech.sharepoint.com/:f:/r/sites/coo/hispec/Shared%20Documents/HISPEC%20-%20Subsystems%20%5BL3%5D/Fiber%20Delivery%20Subsystem%20%5BFIB%5D/Trunk%20Interface%20Box/Datasheets?csf=1&web=1&e=0CtTIQ) in sharepoint. 
- Initial testing seems to suggest that the TEC cools the diode to 25C essentially instantly. 
- Total Current draw of one driver+LD+NH8 was around 0.15A idle, 0.19A lasing.

### Testing Goals
-  How much variability in transmitted power is there with fiber movement, especially at 2330 nm?
- How much attenuation do the TL static attenuators provide at each wavelength?
- How much attenuation do the FVOA and MSOA attenuators provide at each wavelength?
- How repeatable are the variable attenuators and is it a function of wavelength?
- How does the PLC 1x4 fiber splitter work at each wavelength
	- Is the power 25% each?
- How well do the WDM combiners perform? 
	- Combining 1028 + 1270 + 1430?
	- Combining 1430 + 1310 + 2330?
- Can the PLC 1x4 splitter be used as a 3x1 (+unused) WDM combiner and if so how bad are the losses? 

### Testing Setup
1. Connect SM fiber from diode to desired chain of attenuators.
2. Connect desired variable attenuator to FC connections
3. Connect WDM combiner or PLC splitter
4. Connect output to power meter.