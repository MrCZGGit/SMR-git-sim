include ../parameters.mk

cache-raw-size:
	sudo hdparm -a0 -A0 -W0 $(DEVICE)
	sudo fio write.fio --bs=4k --iodepth=1 --filename=$(DEVICE) \
		--write_lat_log=raw-size

map-size:
	sudo hdparm -a0 -A0 -W0 $(DEVICE)
	sudo fio write.fio --bs=4k --iodepth=31 --filename=$(DEVICE) \
		--write_lat_log=map-size

cache-size:
	sudo hdparm -a0 -A0 -W0 $(DEVICE)
	sudo fio write.fio --bs=256k --iodepth=31 --filename=$(DEVICE) \
		--write_lat_log=cache-size

clean:
	rm -rf *.log
