CONTIKI_PROJECT = receiver_root sender
all: $(CONTIKI_PROJECT)

# Use submodule as CONTIKI path
CONTIKI = contiki-ng-brpl

include $(CONTIKI)/Makefile.include
