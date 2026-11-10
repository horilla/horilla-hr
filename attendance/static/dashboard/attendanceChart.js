staticUrl = $("#statiUrl").attr("data-url");
$(document).ready(function () {
    // initializing the department overtime chart.
    var departmentChartData = {
        labels: [],
        datasets: [],
    };
    window["departmentOvertimeChart"] = {};
    const departmentOvertimeChart = document.getElementById(
        "departmentOverChart",
    );
    const themedOptions = ChartTheme.getThemedOptions();
    if (departmentOvertimeChart) {
        var departmentAttendanceChart = new Chart(departmentOvertimeChart, {
            type: "pie",
            data: departmentChartData,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    ...themedOptions.plugins,
                },
            },
            plugins: [
                {
                    afterRender: (departmentAttendanceChart) =>
                        emptyOvertimeChart(departmentAttendanceChart),
                },
            ],
        });
        window["departmentOvertimeChart"] = departmentAttendanceChart
        ChartTheme.observe("departmentOvertimeChart");
    }

    var today = new Date();
    var month = ("0" + (today.getMonth() + 1)).slice(-2);
    var year = today.getFullYear();
    var day = ("0" + today.getDate()).slice(-2);

    function getFormattedDate() {
        var dt = new Date();
        var y = dt.getFullYear();
        var m = ("0" + (dt.getMonth() + 1)).slice(-2);
        var d = ("0" + dt.getDate()).slice(-2);
        return y + "-" + m + "-" + d;
    }

    var currentWeek = getWeekNumber(today);

    $("#attendance_month").val(getFormattedDate());

    $.ajax({
        url: "/attendance/dashboard-attendance",
        type: "GET",
        success: function (response) {
            // Code to handle the response
            dataSet = response.dataSet;
            labels = response.labels;
            createAttendanceChart(response.dataSet, response.labels);
        },
    });

    // Function to update the department overtime chart according to the response fetched from backend.

    function departmentDataUpdate(response) {
        departmentChartData.labels = response.labels;
        departmentChartData.datasets = response.dataset;
        departmentChartData.message = response.message;
        departmentChartData.emptyImageSrc = response.emptyImageSrc;
        if (departmentAttendanceChart) {
            departmentAttendanceChart.update();
        }
    }

    // Function to update the department overtime chart according to the dates provided.

    function changeDepartmentMonth() {
        let type = $("#department_date_type").val();
        let date = $("#department_month").val();
        let end_date = $("#department_month2").val();
        $.ajax({
            type: "GET",
            url: "/attendance/department-overtime-chart/",
            dataType: "json",
            data: {
                date: date,
                type: type,
                end_date: end_date,
            },
            success: function (response) {
                departmentDataUpdate(response);
            },
            error: (error) => { },
        });
    }

    // Function to update the input fields according to type select field.

    function changeDepartmentView(element) {
        var dataType = $(element).val();
        if (dataType === "date_range") {
            $("#department_month").prop("type", "date");
            $("#department_day_input").after(
                '<input type="date" class="mb-2 float-end pointer oh-select ml-2" id="department_month2" style="width: 100px;color:#5e5c5c;"/>',
            );
            $("#department_month").val(getFormattedDate());
            $("#department_month2").val(getFormattedDate());
            changeDepartmentMonth();
        } else {
            $("#department_month2").remove();
            if (dataType === "weekly") {
                $("#department_month").prop("type", "week");
                if (currentWeek < 10) {
                    $("#department_month").val(`${year}-W0${currentWeek}`);
                } else {
                    $("#department_month").val(`${year}-W${currentWeek}`);
                }
                changeDepartmentMonth();
            } else if (dataType === "day") {
                $("#department_month").prop("type", "date");
                $("#department_month").val(getFormattedDate());
                changeDepartmentMonth();
            } else {
                $("#department_month").prop("type", "month");
                $("#department_month").val(`${year}-${month}`);
                changeDepartmentMonth();
            }
        }
    }

    // Function for empty message for department overtime chart.

    function emptyOvertimeChart(departmentAttendanceChart, args, options) {
        var flag = false;
        for (let i = 0; i < departmentAttendanceChart.data.datasets.length; i++) {
            flag =
                flag + departmentAttendanceChart.data.datasets[i].data.some(Boolean);
        }
        if (!flag) {
            const { ctx, canvas } = departmentAttendanceChart;
            departmentAttendanceChart.clear();
            const parent = canvas.parentElement;

            // Set canvas width/height to match
            canvas.width = parent.clientWidth;
            canvas.height = parent.clientHeight;
            // Calculate center position
            const x = canvas.width / 2;
            const y = (canvas.height - 70) / 2;
            var noDataImage = new Image();
            noDataImage.src = departmentAttendanceChart.data.emptyImageSrc
                ? departmentAttendanceChart.data.emptyImageSrc
                : staticUrl + "images/ui/no_records.svg";

            var message = departmentAttendanceChart.data.message
                ? departmentAttendanceChart.data.message
                : i18nMessages.emptyMessages;

            noDataImage.onload = () => {
                // Draw image first at center
                ctx.drawImage(noDataImage, x - 35, y, 70, 70);

                // Draw text below image
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillStyle = "hsl(0,0%,45%)";
                ctx.font = "16px Poppins";
                ctx.fillText(message, x, y + 70 + 30);
            };
        }
    }

    // Ajax request to create department overtime chart initially.

    $.ajax({
        url: "/attendance/department-overtime-chart/",
        type: "GET",
        dataType: "json",
        headers: {
            "X-Requested-With": "XMLHttpRequest",
        },
        success: (response) => {
            departmentDataUpdate(response);
        },
        error: (error) => {
            console.log("Error", error);
        },
    });

    // Functions to update department overtime chart while changing the date input field and select input field.

    $("#departmentChartCard").on("change", "#department_date_type", function (e) {
        changeDepartmentView($(this));
    });

    $("#departmentChartCard").on("change", "#department_month", function (e) {
        changeDepartmentMonth();
    });

    $("#departmentChartCard").on("change", "#department_month2", function (e) {
        changeDepartmentMonth();
    });
});

var data;

function getWeekNumber(date) {
    // Clone the date object to avoid modifying the original
    var clonedDate = new Date(date);
    clonedDate.setHours(0, 0, 0, 0);

    // Set to nearest Thursday: current date + 4 - current day number
    // Make Sunday's day number 7
    clonedDate.setDate(clonedDate.getDate() + 4 - (clonedDate.getDay() || 7));

    // Get first day of year
    var yearStart = new Date(clonedDate.getFullYear(), 0, 1);

    // Calculate full weeks to nearest Thursday
    var weekNumber = Math.ceil(((clonedDate - yearStart) / 86400000 + 1) / 7);

    return weekNumber;
}

var today = new Date();
var month = ("0" + (today.getMonth() + 1)).slice(-2);
var year = today.getFullYear();
var day = ("0" + today.getDate()).slice(-2);

function getGlobalFormattedDate() {
    var dt = new Date();
    var y = dt.getFullYear();
    var m = ("0" + (dt.getMonth() + 1)).slice(-2);
    var d = ("0" + dt.getDate()).slice(-2);
    return y + "-" + m + "-" + d;
}

var currentWeek = getWeekNumber(today);

function createAttendanceChart(dataSet, labels) {
    data = {
        labels: labels,
        datasets: dataSet,
    };

    window["attendanceChart"] = {};

    if (!document.getElementById("dailyAnalytic")) return;

    const ctx = document.getElementById("dailyAnalytic").getContext("2d");
    const themedOptions = ChartTheme.getThemedOptions();

    attendanceChart = new Chart(ctx, {
        type: "bar",
        data: data,
        options: {
            responsive: true,
            scales: {
                x: {
                    ...themedOptions.scales.x,
                },
                y: {
                    ...themedOptions.scales.y,
                },
            },
            plugins: {
                ...themedOptions.plugins,
            },
            onClick: (e, activeEls) => {
                if (!activeEls || activeEls.length === 0) return;

                let datasetIndex = activeEls[0].datasetIndex;
                let dataIndex = activeEls[0].index;
                let datasetLabel = e.chart.data.datasets[datasetIndex].label;
                let label = e.chart.data.labels[dataIndex];

                var parms =
                    "?department=" +
                    datasetLabel +
                    "&type=" +
                    label.toLowerCase().replace(/\s/g, "_");

                var type = $("#type").val();
                const dateStr = $("#attendance_month").val();

                if (type == "weekly") {
                    const [year, week] = dateStr.split("-W");
                    parms = parms + "&week=" + week + "&year=" + year;
                } else if (type == "monthly") {
                    const [year, month] = dateStr.split("-");
                    parms = parms + "&month=" + month + "&year=" + year;
                } else if (type == "day") {
                    parms = parms + "&attendance_date=" + dateStr;
                } else if (type == "date_range") {
                    var start_date = dateStr;
                    var end_date = $("#attendance_month2").val();
                    parms =
                        parms +
                        "&attendance_date__gte=" +
                        start_date +
                        "&attendance_date__lte=" +
                        end_date;
                }

                localStorage.removeItem("savedFilters");

                if (label == "On Time") {
                    $.ajax({
                        url: "/attendance/on-time-view" + parms,
                        type: "GET",
                        data: {
                            input_type: type,
                        },
                        headers: {
                            "X-Requested-With": "XMLHttpRequest",
                        },
                        success: (response) => {
                            $("#back_button").removeClass("d-none");
                            $("#dashboard").html(response);
                        },
                        error: (error) => { },
                    });
                } else {
                    window.location.href =
                        "/attendance/late-come-early-out-view" + parms;
                }
            },
        },
        plugins: [
            {
                afterRender: (chart) => emptyChart(chart),
            },
        ],
    });

    window["attendanceChart"] = attendanceChart
    ChartTheme.observe("attendanceChart");
}

function changeMonth() {
    let type = $("#type").val();
    let date = $("#attendance_month").val();
    let end_date = $("#attendance_month2").val();
    $.ajax({
        type: "GET",
        url: "/attendance/dashboard-attendance/",
        dataType: "json",
        data: {
            date: date,
            type: type,
            end_date: end_date,
        },
        success: function (response) {
            attendanceChart.destroy();
            createAttendanceChart(response.dataSet, response.labels);
        },
        error: (error) => { },
    });
}

function changeView(element) {
    var dataType = $(element).val();
    if (dataType === "date_range") {
        $("#attendance_month").prop("type", "date");
        $("#day_input").after(
            '<input type="date" class="oh-input w-40" id="attendance_month2" onchange="changeMonth(this)"/>',
        );
        $("#attendance_month").val(getGlobalFormattedDate());
        $("#attendance_month2").val(getGlobalFormattedDate());
        changeMonth();
    } else {
        $("#attendance_month2").remove();
        if (dataType === "weekly") {
            $("#attendance_month").prop("type", "week");
            if (currentWeek < 10) {
                $("#attendance_month").val(`${year}-W0${currentWeek}`);
            } else {
                $("#attendance_month").val(`${year}-W${currentWeek}`);
            }
            changeMonth();
        } else if (dataType === "day") {
            $("#attendance_month").prop("type", "date");
            $("#attendance_month").val(getGlobalFormattedDate());
            changeMonth();
        } else {
            $("#attendance_month").prop("type", "month");
            $("#attendance_month").val(`${year}-${month}`);
            changeMonth();
        }
    }
}
if (document.getElementById("pendingHoursCanvas")) {
    var chart = new Chart(document.getElementById("pendingHoursCanvas"), {});
}
window["pendingHoursCanvas"] = chart;
function pendingHourChart(year, month) {
    $.ajax({
        type: "get",
        url: "/attendance/pending-hours/",
        data: { month: month, year: year },
        success: function (response) {
            var ctx = document.getElementById("pendingHoursCanvas");
            if (!ctx) return;
            const themedOptions = ChartTheme.getThemedOptions();
            pendingHoursCanvas.destroy();
            pendingHoursCanvas = new Chart(ctx, {
                type: "bar",
                data: response.data,
                options: {
                    responsive: true,
                    aspectRatio: false,
                    indexAxis: "x",
                    scales: {
                        x: {
                            stacked: true,
                            ...themedOptions.scales.x,
                        },
                        y: {
                            beginAtZero: true,
                            stacked: true,
                            ...themedOptions.scales.y,
                        },
                    },
                    plugins: {
                        ...themedOptions.plugins,
                    },
                },
                plugins: [
                    {
                        afterRender: (chart) => {
                            emptyChart(chart);
                        },
                    },
                ],
            });

            window["pendingHoursCanvas"] = pendingHoursCanvas
            ChartTheme.observe("pendingHoursCanvas");
        },
    });
}

// Create a new Date object
var currentDate = new Date();

// Get the current month (returns a number, where January is 0 and December is 11)
var currentMonthNumber = currentDate.getMonth();
// Create an array of month names
var monthNames = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
];

// Get the current month name
var currentMonth = monthNames[currentMonthNumber];

var currentYearMonth = currentDate.toISOString().slice(0, 7);

$("#hourAccountMonth").val(currentYearMonth);
var currentYear = currentDate.getFullYear();
pendingHourChart(currentYear, currentMonth);
function dynamicMonth(element) {
    var value = element.val();
    var dateArray = value.split("-");
    pendingHourChart(dateArray[0], monthNames[dateArray[1] - 1]);
}
