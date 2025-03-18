// Debug functions
function debugLog(msg) {
  // const debugEl = document.getElementById('debug-info');
  // debugEl.innerHTML += msg + '<br>';
  console.log(msg); // Always log to console for debugging
  
  // Make debug visible by default during troubleshooting
  // document.getElementById('debug-info').style.display = 'block';
}

function toggleDebug() {
  const debugEl = document.getElementById('debug-info');
  debugEl.style.display = debugEl.style.display === 'none' ? 'block' : 'none';
}

// Get track data directly injected as JavaScript array
// let trackPoints = JSON.parse('{{ track_json|safe }}');
debugLog(`Track data loaded with ${trackPoints.length} points`);

// For debugging, log the first point's data structure
if (trackPoints.length > 0) {
  debugLog(`First point structure: ${JSON.stringify(trackPoints[0])}`);
}

// Set initial coordinates from first track point
let initialLat, initialLon;

try {
  if (trackPoints.length > 0) {
    initialLat = trackPoints[0].lat;
    initialLon = trackPoints[0].lon;
    debugLog(`Found coordinates in first point: ${initialLat}, ${initialLon}`);
  } else {
    throw new Error('No track points available');
  }
  
  if (isNaN(initialLat) || isNaN(initialLon)) {
    throw new Error('Initial coordinates are not valid numbers');
  }
} catch (e) {
  debugLog(`Error getting coordinates: ${e.message}`);
  // Fallback to default location if there's an error
  initialLat = 47.14; // Default to somewhere in Liechtenstein
  initialLon = 9.52; 
  debugLog(`Using fallback coordinates: ${initialLat}, ${initialLon}`);
  // Initialize empty track points if needed
  if (!Array.isArray(trackPoints)) {
    trackPoints = [];
    debugLog('Initializing empty trackPoints array');
  }
}

// Initialize map
var map = L.map('map');

// Set view to the first point of the track
map.setView([initialLat, initialLon], 13);
debugLog('Map initialized and centered');

// Add OpenStreetMap tile layer
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; <a href="https://osm.org/copyright">OpenStreetMap</a> contributors'
}).addTo(map);
debugLog('Added tile layer');

// Convert to array of [lat, lon] for Leaflet polyline
var latlngs = trackPoints.map(pt => [pt.lat, pt.lon]);
debugLog(`Created ${latlngs.length} coordinate pairs for polyline`);

// Only draw polyline if we have points
if (latlngs.length > 0) {
  var trackLine = L.polyline(latlngs, {color: 'blue'}).addTo(map);
  debugLog('Added track polyline to map');
  
  // Zoom map to fit track
  map.fitBounds(trackLine.getBounds());
  debugLog('Fitted map bounds to track');
} else {
  debugLog('No track points to display');
}

// Marker variables
var startMarker = null;
var endMarker = null;
var startIndex = null;
var endIndex = null;
var speedMarker = null; // New variable for speed marker
var speedMarkerIndex = null; // Index of speed marker
var speedMarkerActive = false; // Flag for speed marker placement mode
var speedMarkerSaved = false; // Track if speed marker is saved

// Function to find nearest track point index for given lat,lng (simple linear search)
function findNearestPoint(lat, lng) {
  if (latlngs.length === 0) return 0;
  
  let nearestIndex = 0;
  let minDist = Infinity;
  for (let i = 0; i < latlngs.length; i++) {
    let dLat = (latlngs[i][0] - lat);
    let dLng = (latlngs[i][1] - lng);
    let dist = dLat*dLat + dLng*dLng;
    if (dist < minDist) {
      minDist = dist;
      nearestIndex = i;
    }
  }
  return nearestIndex;
}

// Function to store markers in localStorage
function saveMarkers() {
  // Create an object to hold marker data
  const markerData = {};
  let hasMarkers = false;
  
  // Save start and end markers if they exist
  if (startMarker && endMarker) {
    markerData.start = {
      lat: startMarker.getLatLng().lat,
      lng: startMarker.getLatLng().lng
    };
    
    markerData.end = {
      lat: endMarker.getLatLng().lat,
      lng: endMarker.getLatLng().lng
    };
    
    hasMarkers = true;
  }
  
  // Also save speed marker if it exists
  if (speedMarker) {
    markerData.speed = {
      lat: speedMarker.getLatLng().lat,
      lng: speedMarker.getLatLng().lng,
      value: speedMarker.speedValue || 0
    };
    
    speedMarkerSaved = true;
    hasMarkers = true;
    debugLog('Speed marker saved with coordinates');
  }
  
  if (hasMarkers) {
    localStorage.setItem('savedMarkers', JSON.stringify(markerData));
    debugLog('All markers saved to localStorage');
    alert('All markers saved!');
  } else {
    alert('Please place at least one marker before saving');
  }
}

// Function to load markers from localStorage
function loadMarkers() {
  const savedMarkersData = localStorage.getItem('savedMarkers');
  if (savedMarkersData) {
    try {
      const markerData = JSON.parse(savedMarkersData);
      debugLog('Found saved markers in localStorage');
      
      // If we have a track with points
      if (latlngs.length > 0) {
        // Restore markers based only on coordinates
        if (markerData.start) {
          // Find the nearest point on the track to the saved coordinates
          const startPointIndex = findNearestPoint(markerData.start.lat, markerData.start.lng);
          const startCoord = latlngs[startPointIndex];
          startMarker = L.marker(startCoord, {draggable: false, title: 'Start'}).addTo(map);
          startIndex = startPointIndex;
          debugLog(`Restored start marker at coordinates ${markerData.start.lat}, ${markerData.start.lng}`);
        }
        
        if (markerData.end) {
          // Find the nearest point on the track to the saved coordinates
          const endPointIndex = findNearestPoint(markerData.end.lat, markerData.end.lng);
          const endCoord = latlngs[endPointIndex];
          endMarker = L.marker(endCoord, {draggable: false, title: 'End'}).addTo(map);
          endIndex = endPointIndex;
          debugLog(`Restored end marker at coordinates ${markerData.end.lat}, ${markerData.end.lng}`);
        }
        
        // Load speed marker if saved
        if (markerData.speed) {
          const speedPointIndex = findNearestPoint(markerData.speed.lat, markerData.speed.lng);
          const speedCoord = latlngs[speedPointIndex];
          // Create a speed marker icon
          const speedIcon = L.icon({
            iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png',
            shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
            iconSize: [25, 41],
            iconAnchor: [12, 41],
            popupAnchor: [1, -34],
            shadowSize: [41, 41]
          });
          
          speedMarker = L.marker(speedCoord, {
            icon: speedIcon,
            draggable: false,
            title: 'Speed Marker'
          }).addTo(map);
          
          speedMarkerIndex = speedPointIndex;
          
          // Get the speed at this point
          let speed = 0;
          if (trackPoints[speedPointIndex] && typeof trackPoints[speedPointIndex].speed !== 'undefined') {
            speed = trackPoints[speedPointIndex].speed;
          } else if (markerData.speed.value) {
            speed = markerData.speed.value;
          }
          
          speedMarker.speedValue = speed;
          
          // Update speed display
          const speedInfoEl = document.getElementById('speedInfo');
          const speedValueEl = document.getElementById('speedInfoField');
          
          if (speedInfoEl && speedValueEl) {
            speedValueEl.innerText = speed.toFixed(1);
            speedInfoEl.style.display = 'block';
            debugLog(`Restored speed marker with value ${speed.toFixed(1)}`);
          }
          
          // Add popup to marker showing speed
          speedMarker.bindPopup(`Speed: ${speed.toFixed(1)} km/h`).openPopup();
          
          // Mark as saved
          speedMarkerSaved = true;
        }
        
        // Update measurements if both markers exist
        if (startMarker && endMarker) {
          updateMeasurements();
        }
      }
    } catch (e) {
      debugLog(`Error loading saved markers: ${e.message}`);
    }
  } else {
    debugLog('No saved markers found in localStorage');
  }
}

// Function to clear saved markers
function clearMarkers() {
  localStorage.removeItem('savedMarkers');
  
  // Clear and remove start/end markers
  if (startMarker) map.removeLayer(startMarker);
  if (endMarker) map.removeLayer(endMarker);
  startMarker = null;
  endMarker = null;
  startIndex = null;
  endIndex = null;
  
  // Clear and remove speed marker
  if (speedMarker) {
    map.removeLayer(speedMarker);
    speedMarker = null;
    speedMarkerIndex = null;
    speedMarkerSaved = false;
    
    // Hide speed info display
    document.getElementById('speedInfo').style.display = 'none';
  }
  
  document.getElementById('measure-result').innerHTML = "";
  debugLog('All markers cleared');
  alert('All markers cleared!');
}

// Function to toggle speed marker mode
function toggleSpeedMarker() {
  // Toggle the state
  speedMarkerActive = !speedMarkerActive;
  
  debugLog(`Speed marker mode ${speedMarkerActive ? 'activated' : 'deactivated'}`);
  
  // Update button appearance
  const speedMarkerBtn = document.getElementById('speed-marker-btn');
  if (speedMarkerActive) {
    speedMarkerBtn.classList.add('active');
    speedMarkerBtn.innerText = 'Cancel Speed Marker';
  } else {
    speedMarkerBtn.classList.remove('active');
    speedMarkerBtn.innerText = 'Place Speed Marker';
  }
}

// Function to create or update speed marker
function placeSpeedMarker(latlng) {
  // Remove existing speed marker if any
  if (speedMarker) {
    map.removeLayer(speedMarker);
  }
  
  // Find the closest point on the track
  const idx = findNearestPoint(latlng.lat, latlng.lng);
  const coord = latlngs[idx];
  
  debugLog(`Placing speed marker at index ${idx}, coordinates: ${coord}`);
  
  // Get the speed at this point
  let speed = 0;
  if (trackPoints[idx] && typeof trackPoints[idx].speed !== 'undefined') {
    speed = trackPoints[idx].speed;
    debugLog(`Found speed: ${speed} km/h at index ${idx}`);
  } else {
    debugLog(`No speed data found at index ${idx}`);
  }
  
  // Create a custom icon with different color for speed marker
  const speedIcon = L.icon({
    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png',
    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    shadowSize: [41, 41]
  });
  
  // Create the speed marker
  speedMarker = L.marker(coord, {
    icon: speedIcon,
    draggable: false,
    title: 'Speed Marker'
  }).addTo(map);
  
  // Store the index and speed value
  speedMarkerIndex = idx;
  speedMarker.speedValue = speed;
  
  // Reset saved status
  speedMarkerSaved = false;
  
  // Update speed display
  const speedAtMarkerEl = document.getElementById('speedAtMarker');
  
  if (speedAtMarkerEl) {
    speedAtMarkerEl.innerText = speed.toFixed(2);
    debugLog(`Updated speed display with value ${speed.toFixed(1)}`);
  } else {
    debugLog('Error: Could not find speed info elements in DOM');
  }
  
  // Add popup to marker showing speed
  speedMarker.bindPopup(`Speed: ${speed.toFixed(1)} km/h`).openPopup();
  
  // Exit speed marker mode
  toggleSpeedMarker();
}

// Function to update measurement display
function updateMeasurements() {
  if (!startMarker || !endMarker) return;
  
  // Get indices of markers
  var startIdx = startIndex;
  var endIdx = endIndex;
  
  // Ensure startIdx < endIdx
  if (endIdx < startIdx) {
    var tmp = startIdx;
    startIdx = endIdx;
    endIdx = tmp;
  }
  debugLog(`Measuring from index ${startIdx} to ${endIdx}`);
  
  // Calculate distance between these indices
  var totalDist = 0.0;
  for (let j = startIdx; j < endIdx; j++) {
    // Haversine formula in JS:
    let lat1 = latlngs[j][0], lon1 = latlngs[j][1];
    let lat2 = latlngs[j+1][0], lon2 = latlngs[j+1][1];
    let R = 6371000;
    let phi1 = lat1 * Math.PI/180, phi2 = lat2 * Math.PI/180;
    let d_phi = phi2 - phi1;
    let d_lambda = (lon2 - lon1) * Math.PI/180;
    let a = Math.sin(d_phi/2)**2 + Math.cos(phi1)*Math.cos(phi2)*Math.sin(d_lambda/2)**2;
    let c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    let segmentDist = R * c;
    totalDist += segmentDist;
  }
  
  // Time difference in seconds (if time data exists)
  var dtSec = 0;
  var hasTime = trackPoints[startIdx] && trackPoints[endIdx] && 
                trackPoints[startIdx].time && trackPoints[endIdx].time;
  
  if (hasTime) {
    try {
      // Ensure the time strings are in a consistent format (e.g., UTC)
      var t1 = new Date(trackPoints[startIdx].time + 'Z').getTime(); // Append 'Z' for UTC
      var t2 = new Date(trackPoints[endIdx].time + 'Z').getTime(); // Append 'Z' for UTC
      dtSec = Math.max(0, (t2 - t1) / 1000);
      debugLog(`Time difference: ${dtSec} seconds`);
    } catch (e) {
      debugLog(`Error calculating time: ${e.message}`);
      hasTime = false;
    }
  }
  
  if (hasTime && dtSec > 0) {
    // Format time as mm:ss.ms with 0.1 second precision
    const totalSeconds = Math.floor(dtSec);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    const tenthsOfSecond = Math.floor((dtSec - totalSeconds) * 10);
    
    // Format with leading zeros for minutes and seconds
    const formattedMinutes = minutes.toString().padStart(2, '0');
    const formattedSeconds = seconds.toString().padStart(2, '0');
    const formattedTenthsOfSecond = tenthsOfSecond.toString().padEnd(2, '0');
    
    const timeDisplay = `${formattedMinutes}:${formattedSeconds}.${formattedTenthsOfSecond}`;
    
    var avgSpeed = (totalDist/1000) / (dtSec/3600);

    document.getElementById('segmentDistance').innerHTML = (totalDist / 1000).toFixed(3);
    document.getElementById('segmentTime').innerHTML = timeDisplay;
    document.getElementById('segmentAvgSpeed').innerHTML = avgSpeed.toFixed(2);
    
    document.getElementById('marker-alerts').style.display = 'none';
  } else {
    document.getElementById('segmentDistance').innerHTML = 0;
    document.getElementById('segmentTime').innerHTML = 0;
    document.getElementById('segmentAvgSpeed').innerHTML = 0;

    document.getElementById('marker-alerts').style.display = 'block';
    document.getElementById('marker-alert-text').innerHTML = 'No data found, check processed data';
  }
}

// Click event to place markers
map.on('click', function(e) {
  if (latlngs.length === 0) {
    debugLog('No track points available for marking');
    return;
  }
  
  // Check if we're in speed marker mode
  if (speedMarkerActive) {
    debugLog(`Map clicked in speed marker mode at ${e.latlng.lat}, ${e.latlng.lng}`);
    placeSpeedMarker(e.latlng);
    return;
  }
  
  var clickLat = e.latlng.lat, clickLng = e.latlng.lng;
  var idx = findNearestPoint(clickLat, clickLng);
  var coord = latlngs[idx];
  if (!startMarker) {
    // Place start marker
    startMarker = L.marker(coord, {draggable: false, title: 'Start'}).addTo(map);
    startIndex = idx;
    debugLog(`Start marker placed at index ${idx}`);
  } else if (!endMarker) {
    // Place end marker
    endMarker = L.marker(coord, {draggable: false, title: 'End'}).addTo(map);
    endIndex = idx;
    debugLog(`End marker placed at index ${idx}`);
    
    // Once end is set, compute the segment info
    updateMeasurements();
  } else {
    // If both markers exist and user clicks again, reset markers for new selection
    map.removeLayer(startMarker);
    map.removeLayer(endMarker);
    startMarker = null;
    endMarker = null;
    startIndex = null;
    endIndex = null;
    debugLog('Markers reset');
    
    // Place a new start marker at this click
    startMarker = L.marker(coord, {draggable: false, title: 'Start'}).addTo(map);
    startIndex = idx;
    debugLog(`New start marker placed at index ${idx}`);
  }
});

// Function to clear just the speed marker
function clearSpeedMarker() {
  if (speedMarker) {
    map.removeLayer(speedMarker);
    speedMarker = null;
    speedMarkerIndex = null;
    speedMarkerSaved = false;
    
    // Hide speed info display
    const speedInfoEl = document.getElementById('speedInfo');
    if (speedInfoEl) {
      speedInfoEl.style.display = 'none';
    }
    
    debugLog('Speed marker cleared');
    alert('Speed marker cleared!');
  } else {
    alert('No speed marker to clear');
  }
}

// Function to calculate the total distance of the track
function calculateTrackMetrics() {
  // Skip if there are no track points
  if (latlngs.length <= 1) {
    debugLog('Not enough track points to calculate metrics');
    return { 
      length: 0, 
      maxSpeed: 0, 
      avgSpeed: 0 
    };
  }
  
  // Calculate total distance using Haversine formula
  let totalDist = 0;
  let maxSpeed = 0;
  let validSpeedPoints = 0;
  let totalSpeed = 0;
  
  // First check for max speed and gather speed data
  for (let i = 0; i < trackPoints.length; i++) {
    if (trackPoints[i] && typeof trackPoints[i].speed !== 'undefined') {
      const speed = trackPoints[i].speed;
      if (!isNaN(speed) && speed > 0) {
        if (speed > maxSpeed) {
          maxSpeed = speed;
        }
        totalSpeed += speed;
        validSpeedPoints++;
      }
    }
  }
  
  // Calculate total track distance
  for (let i = 0; i < latlngs.length - 1; i++) {
    let lat1 = latlngs[i][0], lon1 = latlngs[i][1];
    let lat2 = latlngs[i+1][0], lon2 = latlngs[i+1][1];
    let R = 6371000; // Earth radius in meters
    
    // Haversine formula
    let phi1 = lat1 * Math.PI/180;
    let phi2 = lat2 * Math.PI/180;
    let d_phi = phi2 - phi1;
    let d_lambda = (lon2 - lon1) * Math.PI/180;
    let a = Math.sin(d_phi/2)**2 + 
            Math.cos(phi1) * Math.cos(phi2) * 
            Math.sin(d_lambda/2)**2;
    let c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    let segmentDist = R * c;
    
    totalDist += segmentDist;
  }
  
  // Calculate average speed (either from speed values or from time if available)
  let avgSpeed = 0;
  
  if (validSpeedPoints > 0) {
    // Calculate from recorded speed values
    avgSpeed = totalSpeed / validSpeedPoints;
  } else {
    // Try to calculate from first and last point timestamps
    const firstPoint = trackPoints[0];
    const lastPoint = trackPoints[trackPoints.length - 1];
    
    if (firstPoint && lastPoint && firstPoint.time && lastPoint.time) {
      try {
        const t1 = new Date(firstPoint.time + 'Z').getTime();
        const t2 = new Date(lastPoint.time + 'Z').getTime();
        const dtHours = (t2 - t1) / (1000 * 60 * 60); // Time difference in hours
        
        if (dtHours > 0) {
          avgSpeed = (totalDist / 1000) / dtHours; // km/h
        }
      } catch (e) {
        debugLog(`Error calculating average speed from timestamps: ${e.message}`);
      }
    }
  }
  
  // Convert distance to kilometers
  const distanceKm = totalDist / 1000;
  
  debugLog(`Track metrics calculated: Length=${distanceKm.toFixed(2)}km, Max Speed=${maxSpeed.toFixed(1)}km/h, Avg Speed=${avgSpeed.toFixed(1)}km/h`);
  
  return {
    length: distanceKm,
    maxSpeed: maxSpeed,
    avgSpeed: avgSpeed
  };
}

document.addEventListener('DOMContentLoaded', function() {
  // Update the points display to show original and processed counts
  const originalPointsEl = document.getElementById('originalPoints');
  if (originalPointsEl && typeof originalPointCount !== 'undefined') {
    originalPointsEl.innerText = originalPointCount;
    debugLog(`Updated original points display to show: ${originalPointCount}`);
  }
  
  const processedPointsEl = document.getElementById('processedPoints');
  if (processedPointsEl) {
    processedPointsEl.innerText = trackPoints.length;
    debugLog(`Updated processed points display to show: ${trackPoints.length}`);
  }
  
  // Calculate and display track metrics
  const trackMetrics = calculateTrackMetrics();
  
  const trackLengthEl = document.getElementById('trackLength');
  if (trackLengthEl) {
    trackLengthEl.innerText = trackMetrics.length.toFixed(2);
  }
  
  const maxSpeedEl = document.getElementById('maxSpeed');
  if (maxSpeedEl) {
    maxSpeedEl.innerText = trackMetrics.maxSpeed.toFixed(2);
  }
  
  const avgSpeedEl = document.getElementById('avgSpeed');
  if (avgSpeedEl) {
    avgSpeedEl.innerText = trackMetrics.avgSpeed.toFixed(2);
  }
  
  // Set up speed marker button
  const speedMarkerBtn = document.getElementById('speed-marker-btn');
  if (speedMarkerBtn) {
    speedMarkerBtn.addEventListener('click', toggleSpeedMarker);
    debugLog('Added event listener to speed marker button');
  } else {
    debugLog('Warning: Could not find speed-marker-btn element');
  }
  
  // Set up clear speed marker button
  const clearSpeedMarkerBtn = document.getElementById('clear-speed-marker-btn');
  if (clearSpeedMarkerBtn) {
    clearSpeedMarkerBtn.addEventListener('click', clearSpeedMarker);
    debugLog('Added event listener to clear speed marker button');
  } else {
    debugLog('Warning: Could not find clear-speed-marker-btn element');
  }
  
  // Set up other buttons
  const saveMarkersBtn = document.getElementById('save-markers-btn');
  if (saveMarkersBtn) {
    saveMarkersBtn.addEventListener('click', saveMarkers);
    debugLog('Added event listener to save markers button');
  }
  
  const clearMarkersBtn = document.getElementById('clear-markers-btn');
  if (clearMarkersBtn) {
    clearMarkersBtn.addEventListener('click', clearMarkers);
    debugLog('Added event listener to clear markers button');
  }
  
  // Try to load saved markers when the page loads
  loadMarkers();
});