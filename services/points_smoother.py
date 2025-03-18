import numpy as np
from functions.haversine import haversine  

import numpy as np
import math
import logging

logger = logging.getLogger(__name__)

def ekf_smooth_track(track_points):
    """
    Apply an Extended Kalman Filter (EKF) to smooth a list of GPS track points.
    Each track point should be a dict with at least 'lat', 'lon', and (optionally) 'time'
    (as a datetime object). The function converts lat/lon to a local Cartesian coordinate
    system (meters), performs EKF filtering, then converts the smoothed positions back to lat/lon.

    Args:
        track_points: List of dicts with keys 'lat', 'lon', and optionally 'time'

    Returns:
        List of dicts with the filtered track. Each point includes:
            - 'lat': filtered latitude
            - 'lon': filtered longitude
            - 'time': original time stamp (if available)
            - 'vx': estimated x-velocity (m/s)
            - 'vy': estimated y-velocity (m/s)
    """
    if not track_points:
        return []

    # Use the first point as the reference for local coordinate conversion.
    ref_lat = track_points[0]['lat']
    ref_lon = track_points[0]['lon']
    # Approximate conversion factors:
    # 1 degree latitude is roughly 111320 meters.
    lat_scale = 111320.0  
    # For longitude, factor in the cosine of the reference latitude (in radians)
    lon_scale = 111320.0 * math.cos(math.radians(ref_lat))

    # Initialize state vector [x, y, vx, vy] in meters and m/s.
    # First point is at (0,0) in the local system.
    state = np.array([0.0, 0.0, 0.0, 0.0])
    # Initial state covariance – you might adjust this based on your system
    P = np.eye(4) * 10.0

    # List to store filtered points; include the reference point
    filtered_points = [{
        'lat': ref_lat,
        'lon': ref_lon,
        'time': track_points[0].get('time'),
        'vx': 0.0,
        'vy': 0.0
    }]

    # Loop through each subsequent measurement.
    for i in range(1, len(track_points)):
        # Compute the elapsed time (dt) in seconds.
        dt = 1.0  # default dt (if no time information)
        t_current = track_points[i].get('time')
        t_prev = track_points[i - 1].get('time')
        if t_current and t_prev:
            dt = (t_current - t_prev).total_seconds()
            if dt <= 0:
                dt = 1.0

        # State transition matrix for constant velocity model.
        F = np.array([[1, 0, dt, 0],
                      [0, 1, 0, dt],
                      [0, 0, 1,  0],
                      [0, 0, 0,  1]])

        # Process noise covariance Q.
        # Assuming acceleration noise standard deviation sigma_a.
        sigma_a = 0.5  # m/s^2 (tweak this parameter as needed)
        Q = np.array([[dt**4/4,       0, dt**3/2,       0],
                      [0,       dt**4/4,       0, dt**3/2],
                      [dt**3/2,       0,    dt**2,       0],
                      [0,       dt**3/2,       0,    dt**2]]) * (sigma_a ** 2)

        # ---------- Prediction Step ----------
        # Predict the next state and covariance.
        state = F @ state
        P = F @ P @ F.T + Q

        # ---------- Update Step ----------
        # Convert the current GPS measurement from lat/lon to local (x, y) in meters.
        meas_lon = track_points[i]['lon']
        meas_lat = track_points[i]['lat']
        z_x = (meas_lon - ref_lon) * lon_scale
        z_y = (meas_lat - ref_lat) * lat_scale
        z = np.array([z_x, z_y])

        # Measurement model h(x) = [x, y]. Since the model is linear in these coordinates,
        # the Jacobian H is simply:
        H = np.array([[1, 0, 0, 0],
                      [0, 1, 0, 0]])

        # Predict measurement from the current state.
        h = np.array([state[0], state[1]])

        # Measurement noise covariance R. Assume GPS position noise ~5m standard deviation.
        sigma_z = 5.0  # m
        R = np.array([[sigma_z ** 2, 0],
                      [0, sigma_z ** 2]])

        # Innovation (measurement residual)
        y_res = z - h

        # Innovation covariance
        S = H @ P @ H.T + R

        # Kalman gain
        K = P @ H.T @ np.linalg.inv(S)

        # Update the state estimate and covariance.
        state = state + K @ y_res
        P = (np.eye(4) - K @ H) @ P

        # Convert the updated local state (x, y) back to lat/lon.
        est_x = state[0]
        est_y = state[1]
        est_lon = ref_lon + est_x / lon_scale
        est_lat = ref_lat + est_y / lat_scale

        filtered_points.append({
            'lat': est_lat,
            'lon': est_lon,
            'time': track_points[i].get('time'),
            'vx': state[2],
            'vy': state[3]
        })

    logger.info(f"EKF smoothing complete: {len(filtered_points)} points processed")
    return filtered_points

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