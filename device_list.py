import sounddevice

host_api = 2
for index, host in enumerate(sounddevice.query_hostapis()):
    if host['name'] == 'ASIO':
        host_api = index

deviceList = []
for device in sounddevice.query_devices():
    if device['hostapi'] == host_api:
        print(device['name'])


