# License : AGPLv3

from rtlsdr_nfs32002.protocol import RtlSdr_NFS32002

def detect():
    print("Ouistici !")

sdr = RtlSdr_NFS32002()
sdr.startDetection(callback=detect)