import pysoem

adapters = pysoem.find_adapters()
for adapter in adapters:
    print(f"Name: {adapter.name}, Desc: {adapter.desc}")