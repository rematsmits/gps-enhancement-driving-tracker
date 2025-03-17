import math
import numpy as np
from scipy.interpolate import PchipInterpolator
from functions.haversine import haversine_distance

def interpolate_speed_idw(points, target_idx, known_idxs, power=2):
    """
    Estimate missing speed at target_idx via Inverse Distance Weighting (IDW).

    :param points: list of dict; each must have:
        - 'cumdist' (float): cumulative horizontal distance from start
        - 'speed' (float or None): known or unknown
    :param target_idx: index where we want to fill speed if it's None or missing.
    :param known_idxs: indices of points with known speed values.
    :param power: exponent in the distance weighting function (typical values 1..3).
    :return: speed (float) or None if no known speeds found.
    """
    if not known_idxs:
        return None
    target_dist = points[target_idx]['cumdist']

    numerator = 0.0
    denominator = 0.0
    for ki in known_idxs:
        spd = points[ki].get('speed')
        if spd is None:
            continue
        dist_diff = abs(points[ki]['cumdist'] - target_dist)
        # If effectively zero distance, return that speed directly
        if dist_diff < 1e-9:
            return spd
        w = 1.0 / (dist_diff**power)
        numerator += w * spd
        denominator += w
    return numerator / denominator if denominator > 0 else None


def refine_points(points,
                  known_time_idxs,
                  known_speed_idxs=None,
                  chunk_size=4):
    """
    Refine a set of GPS points by:
      1. Computing a cumulative horizontal distance ('cumdist').
      2. Splitting into smaller chunks (3-4 known time anchors) for time interpolation.
      3. Interpolating timestamps (via monotonic cubic splines) within each chunk.
      4. Filling missing speeds using weighted IDW from known speeds.

    :param points: list of dict with keys:
        - lat (float)
        - lon (float)
        - time (float or datetime or None) – known or unknown
        - speed (float or None) – known or unknown
      We'll add 'cumdist' internally for distance-based interpolation.
    :param known_time_idxs: indices of points with reliable 'time' (anchor points).
    :param known_speed_idxs: indices of points with reliable 'speed' (optional).
    :param chunk_size: how many known time anchors to process in each chunk (3-4 recommended).
    :return: the same points list, but with updated 'time' and 'speed' where possible.
    """

    n = len(points)
    if n < 2:
        return points

    # 1) Compute cumulative horizontal distance
    cumdist = [0.0] * n
    for i in range(1, n):
        dist_2d = haversine_distance(points[i - 1]['lat'],
                                     points[i - 1]['lon'], points[i]['lat'],
                                     points[i]['lon'])
        cumdist[i] = cumdist[i - 1] + dist_2d
    for i in range(n):
        points[i]['cumdist'] = cumdist[i]

    # 2) Sort known_time_idxs so we process anchors in ascending order
    known_time_idxs = sorted(known_time_idxs)

    # We'll store the updated times in a separate array before assigning
    idx_time = [None] * n
    # Copy known times
    for kt in known_time_idxs:
        idx_time[kt] = points[kt]['time']

    # 3) Chunk-based interpolation for timestamps
    anchor_count = len(known_time_idxs)
    step = chunk_size - 1

    for start in range(0, anchor_count - 1, step):
        end = min(start + chunk_size, anchor_count)
        anchor_idxs = known_time_idxs[start:end]
        if len(anchor_idxs) < 2:
            continue

        # Dist/time at these anchors
        anchor_d = []
        anchor_t = []
        for ai in anchor_idxs:
            anchor_d.append(points[ai]['cumdist'])
            anchor_t.append(points[ai]['time'])

        # Avoid non-increasing distances in case of duplicates
        for j in range(1, len(anchor_d)):
            if anchor_d[j] <= anchor_d[j - 1]:
                anchor_d[j] = anchor_d[j - 1] + 1e-6

        # Convert anchor times to numeric if they're datetime objects
        base_time = None
        numeric_times = []
        for i_t, at in enumerate(anchor_t):
            if i_t == 0:
                if hasattr(at, 'timestamp'):  # datetime
                    base_time = at.timestamp()
                    numeric_times.append(0.0)
                else:
                    base_time = float(at)
                    numeric_times.append(0.0)
            else:
                if hasattr(at, 'timestamp'):
                    numeric_times.append(at.timestamp() - base_time)
                else:
                    numeric_times.append(float(at) - base_time)

        # Build a monotonic spline (distance -> time-in-seconds)
        # time_spline = PchipInterpolator(anchor_d, numeric_times)
        # First remove duplicates or enforce strict monotonicity:
        anchor_d_clean, numeric_times_clean = [], []
        prev_d = None
        for d, t in zip(anchor_d, numeric_times):
            if prev_d is None or d > prev_d + 1e-6:  # small epsilon to handle float precision
                anchor_d_clean.append(d)
                numeric_times_clean.append(t)
                prev_d = d
            else:
                # skip or slightly adjust duplicates
                continue

        # After cleaning, check if we still have at least two points for interpolation
        if len(anchor_d_clean) < 2:
            continue  # skip this chunk, not enough points after cleaning

        # Now create the spline interpolator with cleaned data:
        time_spline = PchipInterpolator(anchor_d_clean, numeric_times_clean)



        # Fill times for points in [anchor_idxs[0], anchor_idxs[-1]]
        left_idx = anchor_idxs[0]
        right_idx = anchor_idxs[-1]
        for pidx in range(left_idx, right_idx + 1):
            if idx_time[pidx] is not None:
                continue
            dist_val = points[pidx]['cumdist']
            sec_val = time_spline(dist_val)
            # Convert back to original scale
            if hasattr(anchor_t[0], 'timestamp'):
                import datetime
                ref_dt = anchor_t[0]
                new_ts = ref_dt.timestamp() + sec_val
                idx_time[pidx] = datetime.datetime.utcfromtimestamp(new_ts)
            else:
                idx_time[pidx] = base_time + sec_val

    # 4) Fallback for any remaining None times (linear interpolation)
    last_known_i = None
    for i in range(n):
        if idx_time[i] is not None:
            last_known_i = i
        else:
            # find next known
            j = i + 1
            while j < n and idx_time[j] is None:
                j += 1
            if last_known_i is not None and j < n:
                # linear interpolation in [last_known_i, j]
                d0 = points[last_known_i]['cumdist']
                d1 = points[j]['cumdist']
                t0 = idx_time[last_known_i]
                t1 = idx_time[j]
                if d1 == d0:
                    idx_time[i] = t0
                else:
                    frac = (points[i]['cumdist'] - d0) / (d1 - d0)
                    if hasattr(t0, 'timestamp'):
                        import datetime
                        delta_sec = (t1 - t0).total_seconds()
                        new_ts = t0.timestamp() + frac * delta_sec
                        idx_time[i] = datetime.datetime.utcfromtimestamp(
                            new_ts)
                    else:
                        idx_time[i] = t0 + frac * (t1 - t0)
            else:
                # can't find a known anchor behind or ahead => remain None
                pass

    # Assign data to points
    for i in range(n):
        points[i]['time'] = idx_time[i]
        points[i]['elevation'] = points[i].get('elevation', None)

    # 5) Fill missing speeds using IDW if known_speed_idxs given
    if known_speed_idxs is None:
        known_speed_idxs = []
    known_speed_idxs = sorted(known_speed_idxs)

    for i in range(n):
        if points[i].get('speed') is None:
            spd_est = interpolate_speed_idw(points,
                                            i,
                                            known_speed_idxs,
                                            power=2)
            points[i]['speed'] = round(spd_est, 1)

    return points
