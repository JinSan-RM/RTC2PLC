def calculate_shape_metrics(border):
    """
    Calculate width, height, and center position from border coordinates.
    
    Args:
        border (list): List of [x, y] coordinate pairs defining the shape boundary.
    
    Returns:
        dict: Dictionary containing width, height, and center coordinates.
    """
    if not border or len(border) < 2:
        return {"width": 0, "height": 0, "center_x": 0, "center_y": 0}

    # Extract x and y coordinates
    x_coords = [point[0] for point in border]
    y_coords = [point[1] for point in border]

    # Calculate width (max x - min x)
    width = max(x_coords) - min(x_coords)

    # Calculate height (max y - min y)
    height = max(y_coords) - min(y_coords)

    # Calculate center (average of min and max x, y)
    center_x = (max(x_coords) + min(x_coords)) / 2
    center_y = (max(y_coords) + min(y_coords)) / 2

    return {
        "width": width,
        "height": height,
        "center_x": center_x,
        "center_y": center_y
    }