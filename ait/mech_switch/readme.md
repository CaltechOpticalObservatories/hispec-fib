# Mechanical Switcher PLC Overview



## Overview of Mechanical Commands:

Note that these likely should be split between a MechanicalSwitcher class and a MainSwitch daemon.
The former handling the hardware, the latter coordinating policy and interaction with the imaging engine.

### Functions
- High Level:
  - Connect with standard policy (daemon/driver decides if time to clean or image)
  - Directly go to specified connection state .
  - Halt (stop all motors)
  - Abort (panic synonym for directly go to disconnected state)
  - Perform Clean and image routine [inner, outer, both], ncleans:
    - Preimage all fibers
    - Clean n times
    - Post image all fibers
  - Image Inner Slit fiber with external camera: slit1, slit2, slit3
  - Clean Inner Slit fibers simultaneously
  - Clean Outer (Input) fibers simultaneously
  - Image Outer fiber with internal camera: splitter1-3, photonic1-3, science1-3 (background, science, speckle), cal fiber
  - Stats and associated reset functions:
    - number of cleans executed by [inner/outer] cleaners (resettable)
    - number of connections executed on fiber (resettable) NB imaging inner/outer fibers does NOT trigger a connection 
      - Note that a connection connects multiple fibers
    - last fiber image path (potentially unknown)
    - last cleaning of fiber
    - Number of cleans of fiber (resettable)
    - PLC State Info:
      - Axis position, velocity
      - air valve setting
      - homed or not
      - auto motion moving
  - Current State:
    - Connections active or current task
  - Settings:
    - connections between cleaning inner
    - connections between cleaning outer
    - imaging frequency
    - air purge state: auto (what this means is tbd, always during motion?), override_off, override_on 
  - Engineering Functions:
    - Move laterally to specified connection position (do not connect), must be in passing position ok to trust PLC if it keeps safe
    - Retract/Insert at current position
    - return to origin
    - set camera observation position
    - set insertion position for fiber connection
    - set post-connection move back amount
    - Switch between automatic and manual operation mode of PLC 
    - Perform homing
      - System likely must be homed after powerup and before first connection, but should automatically perform that at first high level commmand that requires motion
    - Lowest Level Engineering Settings (should not ever need to change):
      - Speed, acceleration, deceleration for each motion
        - passing, insertion start, fiber connect, stable connect, disconnect
  - Alerts:
    - Failure
    - Dirty fiber
    - Fiber image avaialable at
    - Fibers changing connection
    - Fibers connection

## Key notes from spreadsheet shared from manufacturer.

- Always perform a "return to origin" at power on.
- Operation must be confirmed via a status query, the command response does not indicate operation status.
- Documentation suggests there are various operating modes but does document them or switching between them.
- M01: Port Axis
- M02: Inserter Axis


## PLC commanding

The switcher appears to be a Mitsubishi MELSEC PCL using MC type 3E protocol which suggests use of `pymcprotocol` 
will markely make operations more clear: 

```python
from pymcprotocol import Type3E

ip='192.168.0.10'
port=5000

plc = Type3E()
plc.connect(ip, port)

data = plc.batchread_wordunits('W*000000', 14)  # Read 14 words from W*000000

plc.batchwrite_wordunits('W*000014', [0x0104, 0x0102])  # Write a word
```



Updates to the below commands from Dec 25 are in 
https://caltech.sharepoint.com/:x:/r/sites/coo/hispec/Shared%20Documents/HISPEC%20-%20Subsystems%20%5BL3%5D/Fiber%20Delivery%20Subsystem%20%5BFIB%5D/Mechanical%20Switches/Mechanical_switch_users_guide/Final_mechanical_switcher_instructions_and_command_list/%E3%83%95%E3%82%A1%E3%82%A4%E3%83%8F%E3%82%99%E3%83%BC%E4%BA%A4%E6%8F%9B%E5%99%A82025%E4%B8%8A%E4%BD%8D%E9%80%9A%E4%BF%A1%E5%8F%8A%E3%81%B2%E3%82%99GOT%E8%AA%AC%E6%98%8E260611_translated.xlsx?d=w76b10bcdc97f446c86fdbd8d47ef8e52&csf=1&web=1&e=WiTNz9

### Get Status
command: `500000FF03FF000018000004010000W*000000000E`

response: `D00000FF03FF00003C00000104010200010001AFC8000003E80000753000000000000000040010`
- 0-22: Fixed, meaning unspecified.
- 23-26: Target A
- 27-30: Target B
- 31-34: M01 target and position match, inferred binary 0000/0001
- 35-38: M02 status: 3=inserted, 1=removed
- 39-46: hexadecimal, lower 16b word first, words big-endian [low-16][high-16] Position of power switching horizontal axis 32bit positive(?) integer
- 47-54: same for M02/insertion axis
- 55-62: reserved, fixed to 0
- 63-66: 16bit alarm register 1, big-endian
	- 0: Unspecified
	- 1: ALM01 Lifting cylinder error
	- 2: ALM02 Cleaner 1 cylinder error
	- 3: ALM03 Cleaner 2 cylinder error
	- 4-9: Unspecified
	- 10: ALM10 M01 motor driver error
	- 11: ALM11 M01 traverse axis positioning error
	- 12: ALM12 M01 traverse axis homing timeout
	- 13: ALM13 M01 traverse axis positioning timeout
	- 14: Unspecified
	- 15: ALM15 M02 motor driver error
- 67-70: 16bit alarm register 2
	- 0: ALM16 M02 insertion/removal axis positioning error
	- 1: ALM17 M02 insertion/removal axis homing timeout
	- 2: ALM18 M02 insertion/removal axis positioning timeout
	- 3-15: Unspecified
- 71-74: Message Bits
	- 0: MSG00 Please check for an abnormal condition
	- 1: MSG01 Please perform homing (origin return)
	- 2: MSG02 Automatic operation can be started
	- 3: MSG03 Cleaning operation in progress
	- 4: MSG04 Homing (origin return) operation in progress
	- 5: MSG05 Traverse axis (M01) homing search in progress
	- 6: MSG06 Insertion/removal axis (M02) homing search in progress
	- 7-9: Unspecified
	- 10: MSG10 Connector removal operation in progress
	- 11: MSG11 Inserting into No.1 connector in progress
	- 12: MSG12 Inserting into No.2 connector in progress
	- 13: MSG13 Inserting into No.3 connector in progress
	- 14: MSG14 Inserting into No.4 connector in progress
	- 15: MSG15 Inserting into No.5 connector in progress
- 75-78: Message Bits
	- 0: MSG16 Inserting into No.6 connector in progress
	- 1: MSG17 Inserting into No.7 connector in progress
	- 2-4: Unspecified
	- 5: MSG21 Elevating unit is not at the lower limit position
	- 6: MSG22 Cleaner is not at the home position
	- 7-10: Unspecified
	- 11: MSG27 Elevating operation reached the specified number of cycles
	- 12: MSG28 Outer cleaner operation reached the specified number of cycles
	- 13: MSG29 Inner cleaner operation reached the specified number of cycles
	- 14: MSG30 Purge air valve operation reached the specified number of cycles
	- 15: MSG31 Mating operation reached the specified number of cycles
	- 16-23: Unspecified

### Set Target
- command:`500000FF03FF000020000014010000W*0000140002xxxxyyyy`
- port A (xxxx): 0101 -- 0113 (0100 + port number 1-13)
	- 2 unpopulated
-  port B (yyyy): 0101 to 0205 (2 a typo?) (0100 + port number 1-5)
	- 4 unpopulated
- success gets: `D00000FF03FF0000040000`
### Initiate return to origin
- command: `500000FF03FF00001C0000140200000100W*0000120001`
- success gets: D00000FF03FF0000040000
### Retract Fiber at Current Position
- command: `500000FF03FF00001C0000140200000100W*0000120004`
- success gets: D00000FF03FF0000040000
### Insert Fiber at Current Setting Position
- command: `500000FF03FF00001C0000140200000100W*0000120008`
- success gets: D00000FF03FF0000040000
### Stop Motor Operation During Motion
- command: `500000FF03FF00001C0000140200000100W*0000120002`
- success gets: D00000FF03FF0000040000
### Move to Current fiber connection Position
- command: `500000FF03FF00001C0000140200000100W*0000120010`
- success gets: D00000FF03FF0000040000
### Start Cleaning Operation
- command: `500000FF03FF00001C0000140200000100W*000012xxxx`
- xxxx: 0[1-3]20  1=inside, 2=outside, 3=inside and out
- success gets: D00000FF03FF0000040000
### Changing the setting position of the connector insertion/removal axis
- command: `500000FF03FF000020000014010000D*0012280002xxxxxxxx`
	- xxxxxxxx: 32bit hex value lower 16 bits upper 16 bits
	- Sets the distance to move back slightly from the insertion position in multiples of 10 microns
- command: `500000FF03FF000020000014010000D*0012500002xxxxxxxx`
	- xxxxxxxx: 32bit hex value lower 16 bits upper 16 bits
	- Set the insertion position at the port location for camera observation in multiples of 10 um
- command: `500000FF03FF000020000014010000D*0012580002xxxxxxxx`
	- xxxxxxxx: 32bit hex value lower 16 bits upper 16 bits
	- Set the insertion position at the port location for non-camera observation
- success gets: D00000FF03FF0000040000 


## Overview of Fiber Imaging

Switcher uses Lightel DS series cameras that present under linux as UVC (universal video class) webcam devices that 
expose the standard api for additional controls. I believe from initial exploration both auto/manual focus and light 
illumination control was present as was som form of exposure setting. 

I'd encourage the development of a python app that uses open cv to connect to these cameras, grab frames, detect and 
extract the relevant regions.

Two principal algorithmic parts would exist:
- Get a well focused, well exposed image of the fiber end. 
  - While there might be a state branch in the approach between front/back illumination imaging given a specific state focus must be attainable without user intervention. 
  - Detection of front/back illumination can also be done without outside info. 
  - See Jeb/Nem for algorithmic simplicity here. 
- Detect dirt/debris on the fiber end.
  - This is also a simple difference within standard basic cv tooling


HISPEC will want a library of the images but a database is almost certainly unwise. Using a filename schema 
(and folder structure based on either year or month to prevent file-in-folder nuisance issues) will be far more human-friendly.
A simple wrapper of the names for data retrieval/persistence of image and comparison makes this into a "database".

I'd suggest that database be written to via an NFS mount on the rpi.

The program would essentially proceed as follows:
- command to image fiber end against a specified reference image with hint of fiber_position_id
- camera is checked for responsivity and usb power to it is cycled via rPi gpio if necessary. info level log emitted 
- program uses last focus of fiber_id and updates focus as needed, persisting to local text file any update of focus hit
  - error focusing is reported and propagates to requestor
- program obtains image and saves to local (nfs) file system
  - saved images should be exif data stamped with fiber_position_id, focus setting, illumination levels
  - image level should be normalized so human skim of database is not subject to bulk changes.
  - jpg is almost certainly sufficient.
- program compares with reference image and issues alerts as needed
  - settings of what constitutes an issue are coordinated per broader HISPEC settings paradigms
- program publishes image of end and difference with reference over standard publishing (eg.g for an external gui to capture if desired)

Higher-level programs not on rPi would be responsible for:
- any decisions about what to do based on image 
- tracking (or simply rebuilding from the images) a dirtiness score of a fiber with time and with connection count