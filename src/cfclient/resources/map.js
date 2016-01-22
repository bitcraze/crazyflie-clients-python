var map = L.map('map').setView([55.607526, 13.018219], 16);
L.tileLayer('http://otile{s}.mqcdn.com/tiles/1.0.0/map/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution: 'Map data &copy; <a href="http://openstreetmap.org">OpenStreetMap</a> contributors, ' +
        'tiles Courtesy of <a href="http://www.mapquest.com/" target="_blank">MapQuest</a>',
    subdomains: '1',//'1234',
}).addTo(map);

var cf = L.circle([55.607526, 13.018219], 1, {
    color: 'blue',
    fillColor: 'blue',
    fillOpacity: 1
}).addTo(map);

var accuracy = L.circle([55.607526, 13.018219], 0, {
    color: 'red',
    fillColor: '#f03',
    fillOpacity: 0.5
}).addTo(map);

if(typeof MainWindow != 'undefined') {
    var onMapMove = function() { MainWindow.onMapMove(map.getCenter().lat, map.getCenter().lng) };
    map.on('move', onMapMove);
    onMapMove();
}
