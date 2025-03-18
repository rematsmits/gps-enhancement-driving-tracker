import math

# Haversine formula for distance between two lat/lon points (in meters)
def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance between two lat/lon points in meters using Haversine formula"""
    # Earth radius in meters
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(d_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

# Alias for compatibility with the provided refine_points code
# haversine_distance = haversine

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great-circle distance between two lat/lon points (in meters)
    using the Haversine formula.
    """
    R = 6371000.0  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (math.sin(d_phi / 2.0)**2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0)**2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c
