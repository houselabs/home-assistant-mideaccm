# home-assistant-mideaccm
Midea Central Air Conditioner integration for Home Assistant

This component is only support Midea CCM-15.

# Usage
add following configuration to configuration.yaml
```yaml
climate:
  - platform: ccm15
    name: mideaccm
    host: 192.168.1.200
    port: 80
    scan_interval: 10
```
