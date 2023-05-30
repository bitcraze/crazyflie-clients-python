---
title: Parameter Tab
page_id: parameter_tab
sort_order: 4
---

The Crazyflie supports parameters, variables stored in the Crazyflie
that can be changed in real-time. The parameter tab can be used to view
and update parameters. For more information about parameters see
[logging and parameter frameworks](https://www.bitcraze.io/documentation/repository/crazyflie-firmware/master/userguides/logparam/).

![cfclient parameter list](/docs/images/cfclient_param.png)

1.  Parameter information fields
       * *Name:* The name of the parameter or group.
       * *Type:* The C-type of the variable stored in the Crazyflie (you cannot set values outside this)
       * *Access:* RW parameters can be written from the client while RO parameters can only be read
       * *Persistent:* Indicates if it is possible to store this parameter's value in eeprom
       * *Value:* The value of the parameter
2. Group: To make things easier each group has it's members organized as sub-nodes to the group
3. Parameters: The full name of each parameter is the group combined with the name (group.name)
4. The parameter sidebar, here you can set the current value of a parameter. And also store the value to, or clear value from, eeprom if the parameter is persistent
