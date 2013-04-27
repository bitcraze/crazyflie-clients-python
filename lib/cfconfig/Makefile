
######### JTAG and environment configuration ##########
OPENOCD_INTERFACE ?= interface/jtagkey.cfg
OPENOCD_TARGET    ?= target/stm32.cfg
#######################################################

CONFIGFILE        := cblock.cfg
BINFILE           := cblock.bin

help:
	@echo "Crazyflie config block makefile utility"
	@echo
	@echo "This script permits to read and write the config block of Crazyflie using"
	@echo "openocd and any JTAG probe supported by it. The copter has to be connected"
	@echo "to the jtag probe"
	@echo
	@echo "Available action:"
	@echo "   help    : Display this message"
	@echo "   read    : Read the configuration block from the copter using openOCD," 
	@echo "             decode it and save it in a configuration file"
	@echo "   write   : Compile the configuration file to a block and write the block"
	@echo "             in the copter using openOCD"
	@echo
	@echo "Parameters that can be configured: [current value] (can be altered from command line)"
	@echo "   CONFIGFILE    [$(CONFIGFILE)]"
	@echo "   BINFILE       [$(BINFILE)]"
	@echo "   OCD_INTERFACE [$(OPENOCD_INTERFACE)]"
	@echo "   OCD_TARGET    [$(OPENOCD_TARGET)]"

read: readbin bin2cfg

write: cfg2bin writebin

readbin:
	openocd -d0 -f $(OPENOCD_INTERFACE) -f $(OPENOCD_TARGET) -c init -c targets \
	    -c "reset halt" -c "dump_image $(BINFILE) 0x1FC00 1024" \
	    -c "reset run" -c shutdown

writebin:
	openocd -d0 -f $(OPENOCD_INTERFACE) -f $(OPENOCD_TARGET) -c init -c targets  \
	  -c "reset halt" -c "flash erase_sector 0 127 127" \
	  -c "flash write_bank 0 $(BINFILE) 0x1FC00" -c "verify_image $(BINFILE) 0x1FC00" \
	  -c "reset run" -c shutdown
	
bin2cfg:
	./configblock.py extract $(BINFILE) $(CONFIGFILE)

cfg2bin:
	./configblock.py generate $(CONFIGFILE) $(BINFILE)


