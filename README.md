# Firewalla for Home Assistant

This integration allows you to monitor and control your Firewalla devices from Home Assistant. This has been tested on my Firewalla Purple (v1.981) so YMMV - strongly recommend that you test this integration on a dedicated VM or Docker image for that purpose.

## Features

- Monitor device status and connections
- Device tracker support
- Optional: view network flows and statistics
- Optional: get alerts for security events

## Installation

### HACS (Recommended)

1. Make sure you have [HACS](https://hacs.xyz/) installed
2. Go to HACS > Integrations
3. Click the three dots in the top right corner and select "Custom repositories"
4. Add this repository URL: `https://github.com/DaneManes/hass-firewalla`
5. Select "Integration" as the category
6. Click "ADD"
7. Search for "Firewalla" and install it

### Manual Installation

1. Download the latest release from the [releases page](https://github.com/DaneManes/hass-firewalla/releases)
2. Extract the `firewalla` folder from the zip file
3. Copy the `firewalla` folder to your Home Assistant's `custom_components` directory
4. Restart Home Assistant

## Configuration

1. Go to Home Assistant > Settings > Devices & Services
2. Click "Add Integration"
3. Search for "Firewalla" and select it
4. Enter your Firewalla subdomain
   - This is the unique subdomain for your MSP account (the part before .firewalla.net)
5. Enter your Firewalla API token
   - To get your API token, go to your Firewalla MSP account > Account Settings > Create New Token

## Changes to original code

1. The integration no longer creates separate entities for both alarms and rules. They are now blobbed and need a template to display.
2. I've capped the number of alarms returned at 20 - need to put this as a parameter in the setup one day.
3. You will need YAML templates to display the alarms and rules - see below.

## Alarm Display markdown YAML template example

   type: markdown
   content: >-
     ### 🔔 Firewalla Alarm Feed
   
     {% set events = state_attr('sensor.firewalla_recent_alarms', 'recent_events')
     %}
   
     {% if events %}
       {# Change the display of 10 below to however many alarms you need #}
       {% for alarm in events[:10] %}
       **{{ (alarm.time | as_datetime).strftime('%x %X') }} | {{ alarm.device }}**
       {{ alarm.message }}
       
       ***
       {% endfor %}
     {% else %}
       No recent alarms.
     {% endif %}

## Rule Display markdown YAML template example

   type: markdown
   content: >-
     ### 🛡️ Firewalla Rules
   
     **Total:** {{ state_attr('sensor.firewalla_rules', 'total_rules') }} |
     **Active:** {{ state_attr('sensor.firewalla_rules', 'active_rules') }}
   
   
     {% set rules = state_attr('sensor.firewalla_rules', 'rules_list') %}
   
     {% if rules %}
       {% for rule in rules %}
       **{{ '🚫' if rule.action == 'block' else '✅' }} {{ rule.name }}**
       Target: `{{ rule.target }}` ({{ rule.target_type }}) | Scope: {{ rule.scope }}
       
       ***
       {% endfor %}
     {% else %}
       No rules found in attributes.
     {% endif %}

## Firewall API MSP challenges

1. Firewalla does not always return at nice group name for entities where the device has been setup as a "user" on Firewalla. Unfortunately users are not yet returned on the API and you will only get UUID values. There is probably a way to figure this out, but I can live with the limitation at this time.

## Resolving API Issues

To get real data from your Firewalla devices:

1. **Contact Firewalla Support**:
   - Ask about the correct API endpoints for your MSP account
   - Confirm that your API token has the necessary permissions
   - Inquire about any specific API requirements for your account

2. **Check API Documentation**:
   - Verify the correct endpoints in the Firewalla MSP API documentation
   - [Firewalla MSP API Docs](https://docs.firewalla.net)
   - Look for any required parameters or headers that might be missing

3. **Enable Endpoint Discovery**:
   - The integration now attempts to discover the correct API endpoints
   - Check the logs to see if any endpoints were successfully discovered

4. **Enable Debug Logging**:
   Add the following to your `configuration.yaml` to get more detailed logs:
   ```yaml
   logger:
     default: info
     logs:
       custom_components.firewalla: debug
