import numpy as np
from functions.haversine import haversine  

def ekf_smooth_track(matched_points, init_velocity=(0, 0)):
    """
    Smooth a sequence of matched GPS points using an Extended Kalman Filter.
    :param matched_points: list of (lat, lon) coordinates or list of dicts with 'lat' and 'lon' keys.
    :param init_velocity: initial guess for velocity (vx, vy).
    :return: list of smoothed (lat, lon) coordinates.
    """
    # Check input format and extract lat/lon
    is_dict_format = False
    if matched_points and isinstance(matched_points[0], dict):
        is_dict_format = True
        first_point = matched_points[0]
        origin_lat, origin_lon = first_point['lat'], first_point['lon']
    else:
        origin_lat, origin_lon = matched_points[0]
    
    # Convert lat/lon to x,y (e.g., using equirectangular projection around first point for simplicity)
    # This is a simple linear approximation suitable for small areas.
    deg_to_m = 111320  # approximate conversion for degrees to meters (at equator, adjust by cos(lat) for lon)
    
    # Extract coordinates based on input format
    if is_dict_format:
        coords = [((point['lat'] - origin_lat) * deg_to_m,
                  (point['lon'] - origin_lon) * deg_to_m * np.cos(np.radians(origin_lat)))
                 for point in matched_points]
    else:
        coords = [((lat - origin_lat) * deg_to_m,
                  (lon - origin_lon) * deg_to_m * np.cos(np.radians(origin_lat)))
                 for lat, lon in matched_points]

    # Kalman filter initialization
    dt = 1.0  # time step (will be adjusted later if actual timestamps available)
    # State: [x, y, vx, vy]
    x = np.array(
        [coords[0][0], coords[0][1], init_velocity[0], init_velocity[1]],
        dtype=float)
    P = np.eye(4) * 1.0  # initial state covariance
    Q = np.diag(
        [1, 1, 10,
         10])  # process noise covariance (tuned for position and velocity)
    R = np.diag([10,
                 10])  # measurement noise covariance (for observed position)
    F = np.eye(4)  # state transition matrix (will set dt below)
    H = np.zeros((2, 4))  # measurement matrix
    H[0, 0] = 1
    H[1, 1] = 1  # we observe x and y directly

    smooth_coords = []
    prev_x = x.copy()

    for i, (px, py) in enumerate(coords):
        if i > 0:
            # Update F for time step
            F = np.array([[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0],
                          [0, 0, 0, 1]])
            # 1. Predict
            x = F.dot(x)
            P = F.dot(P).dot(F.T) + Q
        # Measurement update with current observed position (px, py)
        z = np.array([px, py])
        y = z - H.dot(x)  # innovation
        S = H.dot(P).dot(H.T) + R  # innovation covariance
        K = P.dot(H.T).dot(np.linalg.inv(S))  # Kalman gain
        x = x + K.dot(y)  # update state estimate
        P = (np.eye(4) - K.dot(H)).dot(P)  # update covariance

        smooth_coords.append((x[0], x[1]))
        
    # Convert filtered coordinates back to lat/lon
    if is_dict_format:
        # Return as dictionaries if input was dictionaries
        smooth_latlon = [
            {'lat': (lat / deg_to_m + origin_lat),
             'lon': (lon / (deg_to_m * np.cos(np.radians(origin_lat))) + origin_lon)}
            for lat, lon in smooth_coords
        ]
    else:
        # Return as tuples if input was tuples
        smooth_latlon = [
            (lat / deg_to_m + origin_lat,
             lon / (deg_to_m * np.cos(np.radians(origin_lat))) + origin_lon)
            for lat, lon in smooth_coords
        ]
        
    return smooth_latlon

# Simple moving-average smoothing for a sequence of latitude/longitude points
def smooth_track(points, window=3):
    """Apply a moving average smoothing filter to a track"""
    if window < 3 or len(points) < window:
        return points  # not enough points to smooth
    
    smoothed = []
    n = len(points)
    half = window // 2
    
    for i in range(n):
        if i < half or i > n-half-1:
            # For the edges, just copy original
            smoothed.append(points[i])
        else:
            # Average over [i-half, ..., i+half]
            lat_sum = lon_sum = 0.0
            for j in range(i-half, i+half+1):
                lat_sum += points[j]['lat']
                lon_sum += points[j]['lon']
            avg_lat = lat_sum / (window)
            avg_lon = lon_sum / (window)
            smoothed.append({'lat': avg_lat, 'lon': avg_lon, 'time': points[i]['time']})
    
    return smoothed