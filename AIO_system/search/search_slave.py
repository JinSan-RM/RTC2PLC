import pysoem

master = pysoem.Master()
master.open('\\Device\\NPF_{C7EBE891-A804-4047-85E5-4D0148B1D3EA}')
if not master.config_init() > 0:
    print("[Error] EtherCAT slaves not found")
else:
    print("Slave Check...")
    for i, slave in enumerate(master.slaves):
        print(f"[slave {i}] vendor id:{slave.man}, product code: {slave.id}, current state: {slave.state}")
        # try:
        #     od = slave.od
        # except pysoem.SdoInfoError:
        #     print('no SDO info for {}'.format(slave.name))
        # else:
        #     print(slave.name)

        #     for obj in od:
        #         print(' Idx: {}; Code: {}; Type: {}; BitSize: {}; Access: {}; Name: "{}"'.format(
        #             hex(obj.index),
        #             obj.object_code,
        #             obj.data_type,
        #             obj.bit_length,
        #             hex(obj.obj_access),
        #             obj.name))
        #         for i, entry in enumerate(obj.entries):
        #             if entry.data_type > 0 and entry.bit_length > 0:
        #                 print('  Subindex {}; Type: {}; BitSize: {}; Access: {} Name: "{}"'.format(
        #                     i,
        #                     entry.data_type,
        #                     entry.bit_length,
        #                     hex(entry.obj_access),
        #                     entry.name))
    master.state = pysoem.INIT_STATE
    master.write_state()
master.close()