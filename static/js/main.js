// Debug functions
function debugLog(msg) {
  const debugEl = document.getElementById('debug-info');
  debugEl.innerHTML += msg + '<br>';
  console.log(msg); // Also log to console for developer debugging
  
  // Make debug visible by default during troubleshooting
  document.getElementById('debug-info').style.display = 'block';
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
var startMarker = null, endMarker = null;
var startIndex = null, endIndex = null;

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
  if (startMarker && endMarker) {
    // Save only marker coordinates, not indices
    const markerData = {
      start: {
        lat: startMarker.getLatLng().lat,
        lng: startMarker.getLatLng().lng
      },
      end: {
        lat: endMarker.getLatLng().lat,
        lng: endMarker.getLatLng().lng
      }
    };
    localStorage.setItem('savedMarkers', JSON.stringify(markerData));
    debugLog('Markers saved to localStorage (coordinate-based)');
    alert('Markers saved!');
  } else {
    alert('Please set both start and end markers before saving');
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
  if (startMarker) map.removeLayer(startMarker);
  if (endMarker) map.removeLayer(endMarker);
  startMarker = null;
  endMarker = null;
  startIndex = null;
  endIndex = null;
  document.getElementById('measure-result').innerHTML = "";
  debugLog('Markers cleared');
  alert('Markers cleared!');
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
  } else {
    debugLog('Time data not available for both points');
  }
  
  // Display results
  var resultText = "Distance: " + (totalDist/1000).toFixed(3) + " km<br/>";
  
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
    
    resultText += "Duration: " + timeDisplay + "<br/>";
    
    var speed = (totalDist/1000) / (dtSec/3600);
    
    // Add a sanity check for unrealistic speeds (over 150 km/h)
    if (speed > 150) {
      debugLog(`Warning: Calculated speed (${speed.toFixed(2)} km/h) seems unrealistic.`);
      resultText += "Average Speed: " + speed.toFixed(2) + " km/h (unrealistic value!)";
    } else {
      resultText += "Average Speed: " + speed.toFixed(2) + " km/h";
    }
  } else {
    resultText += "Time data not available";
  }
  
  document.getElementById('measure-result').innerHTML = resultText;
}

// Click event to place markers
map.on('click', function(e) {
  if (latlngs.length === 0) {
    debugLog('No track points available for marking');
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
    document.getElementById('measure-result').innerHTML = "";
    debugLog('Markers reset');
    
    // Place a new start marker at this click
    startMarker = L.marker(coord, {draggable: false, title: 'Start'}).addTo(map);
    startIndex = idx;
    debugLog(`New start marker placed at index ${idx}`);
  }
});

// Set up buttons
document.getElementById('save-markers-btn').addEventListener('click', saveMarkers);
document.getElementById('clear-markers-btn').addEventListener('click', clearMarkers);

// Try to load saved markers when the page loads
loadMarkers();