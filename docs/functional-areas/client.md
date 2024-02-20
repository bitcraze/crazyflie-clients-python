---
title: Bootloader client implementation
page_id: bootloaderclient
---


## Bootloader file format


In order to make bootloading easier across platforms the different
firmwares are packaged together in a ZIP file that contains a manifest
describing which files are used for what. Here\'s an example of a
manifest, it should be called *manifest.json*:

``` json
{
   "version":2,
   "subversion":1,
   "fw_platform":"cf2",
   "release":"2024.2",
   "files":{
      "cf2-2023.11.bin":{
         "platform":"cf2",
         "target":"stm32",
         "type":"fw",
         "release":"2023.11",
         "repository":"crazyflie-firmware"
      },
      "cf2_nrf-2024.2.bin":{
         "platform":"cf2",
         "target":"nrf51",
         "type":"fw",
         "release":"2024.2",
         "repository":"crazyflie2-nrf-firmware",
         "requires":[
            "sd-s130"
         ]
      },
      "sd130_bootloader-2024.2.bin":{
         "platform":"cf2",
         "target":"nrf51",
         "type":"bootloader+softdevice",
         "release":"2024.2",
         "repository":"crazyflie2-nrf-bootloader",
         "provides":[
            "sd-s130"
         ]
      },
      "lighthouse.bin":{
         "platform":"deck",
         "target":"bcLighthouse4",
         "type":"fw",
         "release":"V6",
         "repository":"lighthouse-fpga"
      },
      "aideck_esp.bin":{
         "platform":"deck",
         "target":"bcAI:esp",
         "type":"fw",
         "release":"2023.06",
         "repository":"aideck-esp-firmware"
      }
   }
}
```

Each entry in the file describes one file, with the following
attributes:


|  Attribute  | Values                            |Comments|
| --------------- | ------------------------------------- | ---------------------- |
|  platform       | cf2, deck                             |Select the target platform, either the main board (CF2) or a deck |
|  target         | stm32, nrf51, <deck>:<cpu>            |Select the target MCU on the target platform|
|  type           | fw, bootloader, bootloader+softdevice |Describe what\'s contained in the binary|
|  release        | A version string                      | The release name of the file |
|  repository     | A repository string                   | The binary's project git repository. If not a complete address, is on the Bitcraze's github project |
|  requires       | A list of requirement                 | Requirement before flashing the firmware. Is used to specify a required softdevice |
|  provices       | A requiremet provided by this file    | Used to describe what a softdevice binary provides |

Currently only platform=cf2, target=stm32, target=nrf51 and type=fw, type=bootloader+softdevice is supported.
