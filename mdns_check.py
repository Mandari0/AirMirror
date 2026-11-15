import time
from zeroconf import Zeroconf, ServiceBrowser, ServiceListener

found = []

class L(ServiceListener):
    def add_service(self, zc, type_, name):
        info = zc.get_service_info(type_, name)
        if info:
            addrs = [a for a in info.parsed_addresses()]
            found.append((name, addrs, info.port, info.server))
            print("FOUND:", name, addrs, "port", info.port, "host", info.server)
        else:
            print("SERVICE (no info yet):", name)

    def update_service(self, zc, type_, name):
        pass

    def remove_service(self, zc, type_, name):
        print("REMOVED:", name)

zc = Zeroconf()
print("Browsing _airplay._tcp.local ...")
b = ServiceBrowser(zc, "_airplay._tcp.local.", L())
time.sleep(8)
zc.close()
print("TOTAL:", len(found))
