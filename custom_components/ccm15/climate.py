"""
Support for Midea's CCM-15 thermostats.
Author: github.com/ohsc
configuration.yaml
climate:
  - platform: ccm15
    name: ccm15
    host: IP_ADDRESS
    port: 80
    scan_interval: 10
"""
import logging
import json
import voluptuous as vol

from homeassistant.components.climate import (ClimateDevice, PLATFORM_SCHEMA)
from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE, HVAC_MODE_COOL, HVAC_MODE_DRY, HVAC_MODE_FAN_ONLY,
    HVAC_MODE_HEAT, SUPPORT_FAN_MODE, HVAC_MODE_AUTO, HVAC_MODE_OFF,
    SUPPORT_TARGET_TEMPERATURE)
from homeassistant.const import (CONF_NAME, CONF_HOST, CONF_PORT,
                                 TEMP_CELSIUS, ATTR_TEMPERATURE)
import homeassistant.helpers.config_validation as cv
import xmltodict
import requests
REQUIREMENTS = ['xmltodict==0.11.0']

DOMAIN = 'ccm15'
_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = 'Midea Thermostat'
DEFAULT_TIMEOUT = 5
BASE_URL = 'http://{0}:{1}{2}'
CONF_URL_STATUS = '/status.xml'
CONF_URL_CTRL = '/ctrl.xml'

ATTR_MODE = 'mode'
CONST_MODE_FAN_AUTO = 'auto'
CONST_MODE_FAN_LOW = 'low'
CONST_MODE_FAN_MIDDLE = 'middle'
CONST_MODE_FAN_HIGH = 'high'
CONST_MODE_FAN_OFF = 'off'

CONST_STATE_CMD_MAP = {HVAC_MODE_COOL:0, HVAC_MODE_HEAT:1, HVAC_MODE_DRY:2, HVAC_MODE_FAN_ONLY:3, HVAC_MODE_OFF:4, HVAC_MODE_AUTO:5}
CONST_CMD_STATE_MAP = {v: k for k, v in CONST_STATE_CMD_MAP.items()}
CONST_FAN_CMD_MAP = {CONST_MODE_FAN_AUTO:0, CONST_MODE_FAN_LOW:2, CONST_MODE_FAN_MIDDLE:3, CONST_MODE_FAN_HIGH:4, CONST_MODE_FAN_OFF:5}
CONST_CMD_FAN_MAP = {v: k for k, v in CONST_FAN_CMD_MAP.items()}

SUPPORT_HVAC = [HVAC_MODE_COOL, HVAC_MODE_HEAT, HVAC_MODE_DRY, HVAC_MODE_FAN_ONLY, HVAC_MODE_OFF, HVAC_MODE_AUTO]

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_HOST, default='192.168.1.200'): cv.string,
    vol.Optional(CONF_PORT, default=80): cv.positive_int,
})

SUPPORT_FLAGS = (SUPPORT_TARGET_TEMPERATURE | SUPPORT_FAN_MODE)

# parse data from ccm bytes
def get_status_from(s):
    locked_wind = 0
    locked_mode = 0
    locked_cold_temp = 0
    locked_hot_temp = 0
    ml = 0
    fl = 0
    ctl = 0
    htl = 0
    rml = 0
    mode = 0
    fan = 0
    temp = 0
    err = 0
    settemp = 0

    if s == '-':
        return None;
    bytesarr = bytes.fromhex(s.strip(','))

    buf = bytesarr[0]
    is_degreeF = (buf >> 0) & 1
    ctl = (buf >> 3) & 0x1f

    buf = bytesarr[1]
    htl = (buf >> 0) & 0x1f
    locked_wind = (buf >> 5) & 7

    buf = bytesarr[2]
    locked_mode = (buf >> 0) & 3
    err = (buf >> 2) & 0x3f

    if locked_mode == 1:
        locked_mode = 0
    elif locked_mode == 2:
        locked_mode = 1
    else:
        locked_mode = -1

    buf = bytesarr[3]
    mode = (buf >> 2) & 7
    fan = (buf >> 5) & 7
    buf = (buf >> 1) & 1
    if buf != 0:
        ml = 1

    buf = bytesarr[4]
    settemp = (buf >> 3) & 0x1f
    DEGREE = "℃"
    if is_degreeF:
        settemp += 62
        ctl += 62
        htl += 62
        DEGREE = "℉"

    buf = bytesarr[5]
    if ((buf >> 3) & 1) == 0:
        ctl = 0
    if ((buf >> 4) & 1) == 0:
        htl = 0
    fl = 0 if ((buf >> 5) & 1) == 0 else 1
    if ((buf >> 6) & 1) != 0:
        rml = 1

    buf = bytesarr[6]
    temp = buf if buf < 128 else buf - 256

    ac = {}
    ac['ac_mode'] = mode
    ac['fan'] = fan
    ac['temp'] = temp
    ac['settemp'] = settemp
    ac['err'] = err
    ac['locked'] = 0
    if ml == 1 or fl == 1 or ctl > 0 or htl > 0 or rml == 1:
        ac['locked'] = 1
    ac['l_rm'] = rml

    ac['l_mode'] = 10 if ml == 0 else locked_mode
    ac['l_wind'] = 10 if fl == 0 else locked_wind

    ac['l_cool_temp'] = ctl
    ac['l_heat_temp'] = htl

    return ac

# poll ac status
def poll_status(host, port):
    resource = BASE_URL.format(
        host,
        port,
        CONF_URL_STATUS)
    data = {}
    try:
        response = requests.get(resource, timeout=10)
        doc = xmltodict.parse(response.text)
        data = doc['response']
    except requests.exceptions.MissingSchema:
        _LOGGER.error("Missing resource or schema in configuration. "
                      "Add http:// to your URL")
        return None
    except requests.exceptions.ConnectionError:
        _LOGGER.error("No route to device at %s", resource)
        return None

    acs = {}
    for ac_name, ac_binary in data.items():
        if len(ac_binary) > 1:
            ac_state = get_status_from(ac_binary)
            if ac_state:
                acs[ac_name] = ac_state

    return acs

# pylint: disable=unused-argument
def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the Midea thermostats."""
    acs = poll_status(config.get(CONF_HOST), config.get(CONF_PORT))
    dev = []

    for ac_name, ac_state in acs.items():
        dev.append(Thermostat(config.get(CONF_NAME), ac_name, config.get(CONF_HOST),
                            config.get(CONF_PORT), ac_state))
    add_devices(dev)


# pylint: disable=abstract-method
# pylint: disable=too-many-instance-attributes
class Thermostat(ClimateDevice):
    """Representation of a Midea thermostat."""

    def __init__(self, name, ac_name, host, port, acdata):
        """Initialize the thermostat."""
        self._name = '{}_{}'.format(name, ac_name)
        self._ac_name = ac_name
        self._ac_id = 2 ** (int(ac_name.strip('a')))
        self._host = host
        self._port = port
        self._hvac_list = SUPPORT_HVAC
        self._fan_list = [CONST_MODE_FAN_OFF, CONST_MODE_FAN_AUTO, CONST_MODE_FAN_LOW, CONST_MODE_FAN_MIDDLE, CONST_MODE_FAN_HIGH]
        self._current_setfan = CONST_MODE_FAN_AUTO
        self.updateWithAcdata(acdata)
        _LOGGER.debug("Init called")
        self.update()

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_FLAGS

    @property
    def should_poll(self):
        """Polling needed for thermostat."""
        _LOGGER.debug("Should_Poll called")
        return True

    def updateWithAcdata(self, acdata):
        """Update self data with acdata"""
        self._current_temp = acdata['temp']
        self._current_settemp = acdata['settemp']
        self._current_state = CONST_CMD_STATE_MAP[acdata['ac_mode']]
        self._current_fan = CONST_CMD_FAN_MAP[acdata['fan']]
        if self._current_fan != CONST_MODE_FAN_OFF:
            self._current_setfan = self._current_fan

    def update(self):
        """Update the data from the thermostat."""
        acdata = poll_status(self._host, self._port)[self._ac_name]
        self.updateWithAcdata(acdata)
        _LOGGER.debug("Update called")

    def setStates(self):
        """Set new target states."""
        state_cmd = CONST_STATE_CMD_MAP[self._current_state]
        fan_cmd = CONST_FAN_CMD_MAP[self._current_fan]

        url = BASE_URL.format(
            self._host,
            self._port,
            CONF_URL_CTRL +
            '?ac0=' + str(self._ac_id) +
            '&ac1=0' +
            '&mode=' + str(state_cmd) +
            '&fan=' + str(fan_cmd) +
            '&temp=' + str(self._current_settemp)
            )
        _LOGGER.info("Set state=%s", url)
        req = requests.get(url, timeout=DEFAULT_TIMEOUT)
        if req.status_code != requests.codes.ok:
            _LOGGER.exception("Error doing API request")
        else:
            _LOGGER.debug("API request ok %d", req.status_code)

    @property
    def name(self):
        """Return the name of the thermostat."""
        return self._name

    @property
    def device_state_attributes(self):
        """Return the device specific state attributes."""
        return {
            ATTR_MODE: self._current_state
        }

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return TEMP_CELSIUS

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._current_temp

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._current_settemp

    def set_temperature(self, **kwargs):
        """Set new target temperature."""
        import math
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        else:
            self._current_settemp = int(math.ceil(temperature)) if temperature > self._current_settemp else int(math.floor(temperature))
            self.setStates()
            self.async_write_ha_state()

    @property
    def hvac_mode(self):
        """Return the current state of the thermostat."""
        return self._current_state

    def set_hvac_mode(self, hvac_mode):
        """Set hvac mode."""
        if hvac_mode not in CONST_STATE_CMD_MAP:
            hvac_mode = HVAC_MODE_OFF
        if self._current_state != hvac_mode and self._current_fan == CONST_MODE_FAN_OFF:
            self._current_fan = self._current_setfan
        self._current_state = hvac_mode
        self.setStates()
        self.async_write_ha_state()
        return

    @property
    def hvac_modes(self):
        """List of available hvac modes."""
        return self._hvac_list

    @property
    def fan_mode(self):
        """Return the fan setting."""
        return self._current_fan

    def set_fan_mode(self, fan):
        """Set new target fan mode."""
        if self._current_state == HVAC_MODE_OFF:
            return
        if fan not in CONST_FAN_CMD_MAP:
            fan = CONST_MODE_FAN_AUTO
        if fan == CONST_MODE_FAN_OFF:
            self._current_state = HVAC_MODE_OFF

        self._current_fan = fan

        if self._current_fan != CONST_MODE_FAN_OFF:
            self._current_setfan = self._current_fan

        self.setStates()
        self.async_write_ha_state()
        return

    @property
    def fan_modes(self):
        """Return the list of available fan modes."""
        return self._fan_list

