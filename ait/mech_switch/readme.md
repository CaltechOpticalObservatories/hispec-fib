# Mechanical Switcher PLC Overview


## Key notes from spreadsheet shared from manufacturer.

- Always perform a "return to origin" at power on.
- Operation must be confirmed via a status query, the command response does not indicate operation status.
- Documentation suggests there are various operating modes but does document them or switching between them.
- M01: Port Axis
- M02: Inserter Axis


## Commands

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


## Control
The switcher appears to be a Mitsubishi MELSEC PCL using MC type 3E protocol which suggests use of `pymcprotocol` could clean up operations 

```python
from pymcprotocol import Type3E

ip='192.168.0.10'
port=5000

plc = Type3E()
plc.connect(ip, port)

data = plc.batchread_wordunits('W*000000', 14)  # Read 14 words from W*000000

plc.batchwrite_wordunits('W*000014', [0x0104, 0x0102])  # Write a word
```

