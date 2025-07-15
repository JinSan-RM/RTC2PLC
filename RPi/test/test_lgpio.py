import lgpio

def test_lgpio():
    h = lgpio.gpiochip_open(0)
    if h < 0:
        raise RuntimeError(f"GPIO open error. errorcode: {h}")
    
    status, num_of_lines, name, label = lgpio.gpio_get_chip_info(h)
    if status < 0:
        raise RuntimeError(f"GPIO info error. errorcode: {status}")
        
    print(f"GPIO info: enable pins[{num_of_lines}], name[{name}], label[{label}]")

if __name__ == "__main__":
    test_lgpio()