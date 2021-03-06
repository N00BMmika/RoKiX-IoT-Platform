# The MIT License (MIT)
#
# Copyright (c) 2018 Kionix Inc.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy 
# of this software and associated documentation files (the "Software"), to deal 
# in the Software without restriction, including without limitation the rights 
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell 
# copies of the Software, and to permit persons to whom the Software is 
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in 
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR 
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, 
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE 
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER 
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN 
# THE SOFTWARE.
# Example app for freefall detection
# KX122
# Freefall detection uses interrupt intx
###
import imports  # pylint: disable=unused-import
from kx_lib import kx_logger
from kx_lib.kx_configuration_enum import POLARITY_DICT, CFG_POLARITY
from kx_lib.kx_util import get_other_pin_index, convert_to_enumkey
from kx_lib.kx_data_stream import StreamConfig
from kx_lib.kx_data_logger import SingleChannelEventReader
from kx022.kx022_driver import KX022Driver
from kx022.kx022_driver import r122, b122, e122, m122


LOGGER = kx_logger.get_logger(__name__)
# LOGGER.setLevel(kx_logger.DEBUG)



class Parameter_set_1:
    # pylint: disable=bad-whitespace
    LOW_POWER_MODE              = False
    odr_OSA                     = 25
    odr_OFFI                    = 100
    lp_average                  = '16_SAMPLE_AVG'
    FF_THRESHOLD_VALUE          = 8                                 # threshold
    FF_COUNTER_VALUE            = 5                                 # timer (100Hz)
    FFCNTL_ULMODE               = b122.KX122_FFCNTL_ULMODE
    FFCNTL_DCRM                 = b122.KX122_FFCNTL_DCRM


class KX122FFStream(StreamConfig):
    fmt = "BBBBB"
    hdr = "ch!ins2!ins3!stat!int_rel"
    reg = r122.KX122_INS2

    def __init__(self, sensors, pin_index=2, timer=None):
        assert sensors[0].name in KX022Driver.supported_parts
        StreamConfig.__init__(self, sensors[0])
        assert not timer, 'Timer not supported in this data stream'

        # get pin_index if it is not given and timer is not used
        if pin_index is None and timer is None:
            pin_index = get_other_pin_index()

        assert pin_index in [1, 2], 'got %s' % pin_index

        self.define_request_message(
            fmt=self.fmt,
            hdr=self.hdr,
            reg=self.reg,
            pin_index=pin_index)


def disable_freefall(sensor):
    sensor.reset_bit(r122.KX122_FFCNTL, b122.KX122_FFCNTL_FFIE)         # freefall disable


def enable_freefall(sensor,
                    cfg=Parameter_set_1,
                    int_pin=2,
                    power_off_on=True):

    LOGGER.info('Freefall event init start')
    #
    # Parameter validation
    #

    assert convert_to_enumkey(cfg.odr_OSA) in e122.KX122_ODCNTL_OSA.keys(),\
        'Invalid odr_OSA value "{}". Valid values are {}'.format(
        cfg.odr_OSA, e122.KX122_ODCNTL_OSA.keys())

    assert convert_to_enumkey(cfg.odr_OFFI) in e122.KX122_FFCNTL_OFFI.keys(),\
        'Invalid odr_OFFI value "{}". Valid values are {}'.format(
        cfg.odr_OFFI, e122.KX122_FFCNTL_OFFI.keys())

    assert cfg.lp_average in e122.KX122_LP_CNTL_AVC.keys(),\
        'Invalid lp_average value "{}". Valid values are {}'.format(
        cfg.lp_average, e122.KX122_LP_CNTL_AVC.keys())

    assert cfg.LOW_POWER_MODE in [True, False],\
        'Invalid LOW_POWER_MODE value "{}". Valid values are {}'.format(
        cfg.LOW_POWER_MODE, [True, False])

    # Set sensor to stand-by to enable setup change
    if power_off_on:
        sensor.set_power_off()  # Set sensor to stand-by to enable setup change

    #
    # Configure sensor
    #

    # stream odr (if stream odr is biggest odr, it makes effect to current consumption)
    sensor.set_odr(e122.KX122_ODCNTL_OSA[convert_to_enumkey(cfg.odr_OSA)])

    # g-range is fixed +-8g

   # resolution / power mode selection
    # Set performance mode (To change value, the PC1 must be first cleared to set stand-by mode)
    if cfg.LOW_POWER_MODE:
        sensor.reset_bit(r122.KX122_CNTL1, b122.KX122_CNTL1_RES)              # low current
        sensor.set_average(e122.KX122_LP_CNTL_AVC[cfg.lp_average])         # lowest current mode average
    else:
        sensor.set_bit(r122.KX122_CNTL1, b122.KX122_CNTL1_RES)                # high resolution

    # Free fall setup
    sensor.set_bit(r122.KX122_FFCNTL, b122.KX122_FFCNTL_FFIE)         # freefall enable
    sensor.set_bit(r122.KX122_FFCNTL, cfg.FFCNTL_ULMODE)       # latched int
    sensor.set_bit(r122.KX122_FFCNTL, cfg.FFCNTL_DCRM)
    sensor.set_bit_pattern(r122.KX122_FFCNTL,
                           e122.KX122_FFCNTL_OFFI[convert_to_enumkey(cfg.odr_OFFI)],
                           m122.KX122_FFCNTL_OFFI_MASK)            # freefall odr
    sensor.write_register(r122.KX122_FFTH, cfg.FF_THRESHOLD_VALUE)  # freefall threshold
    sensor.write_register(r122.KX122_FFC, cfg.FF_COUNTER_VALUE)    # freefal timer

    # interrupt pin and visibility
    if int_pin == 1:
        sensor.reset_bit(r122.KX122_INC1, b122.KX122_INC1_IEL1)           # int1 latched interrupt
        sensor.set_bit(r122.KX122_INC4, b122.KX122_INC4_FFI1)             # freefall to int1 pin
        sensor.set_bit(r122.KX122_INC1, b122.KX122_INC1_IEN1)             # enable int1
    else:  # int_pin==2
        sensor.reset_bit(r122.KX122_INC5, b122.KX122_INC5_IEL2)           # int2 latched interrupt
        sensor.set_bit(r122.KX122_INC6, b122.KX122_INC6_FFI2)             # freefall to int2 pin
        sensor.set_bit(r122.KX122_INC5, b122.KX122_INC5_IEN2)             # enable int2

    polarity = POLARITY_DICT[sensor.resource[CFG_POLARITY]]
    LOGGER.debug('Configuring interrupt polarity {}'.format(
        sensor.resource[CFG_POLARITY]))
    sensor.set_interrupt_polarity(intpin=int_pin, polarity=polarity)

    #
    # Turn on operating mode (disables setup)
    #
    if power_off_on:
        sensor.set_power_on()

    # sensor.register_dump()#;sys.exit()

    LOGGER.info('\nFreefall detection enabled')

    sensor.release_interrupts()                             # clear all internal function interrupts


class KX122FFLogger(SingleChannelEventReader):

    def enable_data_logging(self, **kwargs):
        enable_freefall(self.sensors[0], **kwargs)


def main():
    app = KX122FFLogger([KX022Driver])
    app.enable_data_logging()
    app.run(KX122FFStream)


if __name__ == '__main__':
    main()
