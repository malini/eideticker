"use strict";

function parseDate(datestr) {
  var parsed = datestr.split("-");
  var year = parsed[0];
  var month = parsed[1] - 1; //Javascript months index from 0 instead of 1
  var day = parsed[2];

  return Date.UTC(year, month, day);
}

function updateContent(graphTitle, deviceId, testId, measureId) {

  var measureDescription;
  if (measureId === "checkerboard") {
    measureDescription = 'The measure is the sum of the percentages of frames that are checkerboarded over the entire capture. Lower values are better.';
  } else if (measureId === "fps") {
    measureDescription = 'The measure is a calculation of the average number of UNIQUE frames per second of capture. The theoretical maximum is 60 fps (which is what we are capturing), but note that if there periods where the page being captured is unchanging this number may be aritifically low.';
  } else {
    measureDescription = 'The measure is a calculation of the total number of UNIQUE frames in the capture. Higher values generally indicate more fluid animations.';
  }

  $('#content').html(ich.graph({'title': graphTitle,
                                'measureDescription': measureDescription
                               }));
  $('#measure-'+measureId).attr("selected", "true");
  $('#measure').change(function() {
    var newMeasure = $(this).val();
    window.location.hash = '/' + [ deviceId, testId, newMeasure ].join('/');
  });
}

function updateGraph(rawdata, measure) {
  // show individual data points
  var graphdata = [];
  var color = 0;
  var metadataHash = {};

  var seriesIndex = 0;
  var minMaxDates;
  Object.keys(rawdata).sort().forEach(function(type) {
    metadataHash[seriesIndex] = [];

    // point graph
    var series1 = {
      label: type,
      points: { show: true },
      color: color,
      data: []
    };


    var prevRevision = null;
    Object.keys(rawdata[type]).sort().forEach(function(datestr) {
      rawdata[type][datestr].forEach(function(sample) {
        series1.data.push([ parseDate(datestr), sample[measure] ]);
        metadataHash[seriesIndex].push({
          'videoURL': sample.video,
          'dateStr': datestr,
          'appDate': sample.appdate,
          'revision': sample.revision,
          'prevRevision': prevRevision,
          'buildId': sample.buildid,
          'profileURL': sample.profile
        });
      });
      prevRevision = rawdata[type][datestr][0].revision;
    });
    graphdata.push(series1);

    var dates = series1.data.map(function(d) { return d[0]; });
    minMaxDates = [ Math.min.apply(null, dates), Math.max.apply(null, dates) ];

    // line graph (aggregate average per day)
    var series2 = {
      hoverLabel: "Average per day for " + type,
      lines: { show: true },
      color: color,
      data: [],
      clickable: false,
      hoverable: false
    };
    Object.keys(rawdata[type]).forEach(function(datestr) {
      var numSamples = 0;
      var total = 0;
      rawdata[type][datestr].forEach(function(sample) {
        total += sample[measure];
        numSamples++;
      });

      series2.data.push([parseDate(datestr), total/numSamples]);
    });
    series2.data.sort();
    graphdata.push(series2);

    color++;
    seriesIndex += 2;
  });

  var axisLabel;
  if (measure == "checkerboard") {
    axisLabel = "Checkerboard";
  } else if (measure === "uniqueframes") {
    axisLabel = "Unique frames";
  } else {
    axisLabel = "Frames per second";
  }

  var plot = $.plot($("#graph-container"), graphdata, {
    xaxis: {
      mode: "time",
      timeformat: "%0m-%0d"
    },
    yaxis: {
      axisLabel: axisLabel,
      min: 0
    },
    legend: {
      container: $("#legend"),
    },
    grid: { clickable: true, hoverable: true },
    zoom: { interactive: true },
    pan: { interactive: true }
  });

    // add zoom out button
  $('<div class="button" style="right:20px;top:20px">zoom out</div>').appendTo($("#graph-container")).click(function (e) {
        e.preventDefault();
        plot.zoomOut();
  });

  function showTooltip(x, y, contents) {
      $('<div id="tooltip">' + contents + '</div>').css( {
          position: 'absolute',
          display: 'none',
          top: y + 5,
          left: x + 5,
          border: '1px solid #fdd',
          padding: '2px',
          'background-color': '#fee',
          opacity: 0.80
      }).appendTo("body").fadeIn(200);
  }

  // Plot Hover tooltip
  var previousPoint = null;
  $("#graph-container").bind("plothover", function (event, pos, item) {
    if (item) {
      if (previousPoint != item.dataIndex) {
        var toolTip;
        var x = item.datapoint[0].toFixed(2),
            y = item.datapoint[1].toFixed(2);

        if (metadataHash[item.seriesIndex] && metadataHash[item.seriesIndex][item.dataIndex]) {
          var metadata = metadataHash[item.seriesIndex][item.dataIndex];
          toolTip = (item.series.label || item.series.hoverLabel) + " of " + (metadata.appDate || "'Unknown Date'") + " = " + y;
        } else {
          console.log(JSON.stringify(item.series));
          toolTip = (item.series.label || item.series.hoverLabel) + " = " + y;
        }

        previousPoint = item.dataIndex;

        $("#tooltip").remove();
        showTooltip(item.pageX, item.pageY, toolTip);
      }
    } else {
      $("#tooltip").remove();
      previousPoint = null;
    }
  });

  $("#graph-container").bind("plotclick", function (event, pos, item) {
    plot.unhighlight();
    if (item) {
      var metadata = metadataHash[item.seriesIndex][item.dataIndex];
      $('#datapoint-info').html(ich.graphDatapoint({ 'videoURL': metadata.videoURL,
                                                     'profileURL': metadata.profileURL,
                                                     'measureName': measure,
                                                     'date': metadata.dateStr,
                                                     'appDate': metadata.appDate,
                                                     'revision': metadata.revision,
                                                     'prevRevision': metadata.prevRevision,
                                                     'buildId': metadata.buildId,
                                                     'measureValue': Math.round(100.0*item.datapoint[1])/100.0
                                                   }));
      $('#video').css('width', $('#video').parent().width());
      $('#video').css('max-height', $('#graph-container').height());

      plot.highlight(item.series, item.datapoint);
    } else {
      $('#datapoint-info').html(null);
    }
  });
}

$(function() {
  var testInfoDict = {
    'taskjs-scrolling': {
      'key': 'taskjs',
      'graphTitle': 'Scrolling on taskjs.org',
      'defaultMeasure': 'checkerboard'
    },
    'nightly-zooming': {
      'key': 'nightly',
      'graphTitle': 'Mozilla Nightly Zooming Test',
      'defaultMeasure': 'checkerboard'
    },
    'nytimes-scrolling': {
      'key': 'nytimes-scroll',
      'graphTitle': 'New York Times Scrolling Test',
      'defaultMeasure': 'checkerboard'
    },
    'nytimes-zooming': {
      'key': 'nytimes-zoom',
      'graphTitle': 'New York Times Zooming Test',
      'defaultMeasure': 'checkerboard'
    },
    'cnn': {
      'key': 'cnn',
      'graphTitle': 'CNN.com Test',
      'defaultMeasure': 'checkerboard'
    },
    'canvas-clock': {
      'key': 'clock',
      'graphTitle': 'Canvas Clock Test',
      'defaultMeasure': 'fps'
    },
    'reddit': {
      'key': 'reddit',
      'graphTitle': 'Reddit test',
      'defaultMeasure': 'checkerboard'
    },
    'imgur': {
      'key': 'imgur',
      'graphTitle': 'imgur test',
      'defaultMeasure': 'checkerboard'
    },
    'wikipedia': {
      'key': 'wikipedia',
      'graphTitle': 'wikipedia test',
      'defaultMeasure': 'checkerboard'
    }
  }

  Object.keys(testInfoDict).forEach(function(testkey) {
    $('<li id="' + testkey + '-li" testid = ' + testkey + '><a>' + testkey + '</a></li>').appendTo($('#test-chooser'));
  });

  var graphData = {};
  $.getJSON('devices.json', function(rawData) {
    var devices = rawData['devices'];
    var deviceIds = Object.keys(devices);
    var routes = {};
    deviceIds.forEach(function(deviceId) {
      $('<li id="device-' + deviceId + '-li" deviceid= ' + deviceId + '><a>'+devices[deviceId].name+'</a></li>').appendTo($('#device-chooser'));

      var baseRoute = "/(" + deviceId + ")/(" + Object.keys(testInfoDict).join("|") + ")";
      routes[baseRoute] = {
        '/(checkerboard|fps|uniqueframes)': {
          on: function(deviceId, testId, measure) {
            // update all links to be relative to the new test or device
            $('#device-chooser').children('li').removeClass("active");
            $('#device-chooser').children('#device-'+deviceId+'-li').addClass("active");
            $('#device-chooser').children('li').each(function() {
              $(this).children('a').attr('href', '#/' + [ $(this).attr('deviceid'),
                                                          testId,
                                                          measure ].join('/'));
            });

            $('#test-chooser').children('li').removeClass("active");
            $('#test-chooser').children('#'+testId+'-li').addClass("active");

            $('#test-chooser').children('li').each(function() {
              var testIdAttr = $(this).attr('testid');
              if (testIdAttr) {
                var defaultMeasure = testInfoDict[testIdAttr].defaultMeasure;
                $(this).children('a').attr('href', '#/' +
                                           [ deviceId, testIdAttr,
                                             defaultMeasure ].join('/'));
              }
            });

            var testInfo = testInfoDict[testId];
            updateContent(testInfo.graphTitle, deviceId, testId, measure);

            // update graph
            $.getJSON('data-' + deviceId + '.json', function(graphDataForDevice) {
              updateGraph(graphDataForDevice[testInfo.key], measure);
            });
          }
        }
      }
    });

    var defaultDeviceId = deviceIds[0];
    // HACK: try to default to the LG-P999 for now
    deviceIds.forEach(function(deviceId) {
      if (devices[deviceId].name === "LG-P999") {
        defaultDeviceId = deviceId;
      }
    });

    var router = Router(routes).init('/' + defaultDeviceId + '/taskjs-scrolling/checkerboard');
  });
});
