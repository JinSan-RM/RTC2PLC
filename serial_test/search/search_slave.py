import pysoem

master = pysoem.Master()
master.open('\\Device\\NPF_{82D71BA4-0710-4E4A-9ED2-4FD7DA4F0FD3}')
if not master.config_init() > 0:
    print("[Error] EtherCAT slaves not found")
else:
    print("Slave Check...")
    for i, slave in enumerate(master.slaves):
        print(f"[slave {i}] vendor id:{slave.man}, product code: {slave.id}, current state: {slave.state}")
    master.state = pysoem.INIT_STATE
    master.write_state()
master.close()