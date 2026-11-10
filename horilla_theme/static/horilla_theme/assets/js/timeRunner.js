// The element is missing (or its value empty) for a user with no employee
// record or attendance history; treat that as zero worked seconds, not NaN.
var at_work_seconds = parseInt($(".at_work_seconds").data("at-work-seconds"), 10) || 0;
var run = $(".at_work_seconds").data("run");
var whiteLabelCompany = $("#whiteLabelCompany").data("company");

// time-runner
function secondsToDuration(seconds) {
    seconds = Number(seconds);
    if (!isFinite(seconds) || seconds < 0){
        seconds = 0
    }
    var hours = Math.floor(seconds / 3600);
    var minutes = Math.floor((seconds % 3600) / 60);
    var remainingSeconds = Math.floor(seconds % 60);

    // add leading zeros if necessary
    var formattedHours = (hours < 10) ? "0" + hours : hours;
    var formattedMinutes = (minutes < 10) ? "0" + minutes : minutes;
    var formattedSeconds = (remainingSeconds < 10) ? "0" + remainingSeconds : remainingSeconds;

    return formattedHours + ":" + formattedMinutes + ":" + formattedSeconds;
}
// accessing initial worked hours from the user
$(".time-runner").not("title").html(secondsToDuration(at_work_seconds));
$("title.time-runner").html(` ${whiteLabelCompany} | ` + secondsToDuration(at_work_seconds));
if (run) {
    setInterval(() => {
        at_work_seconds = parseInt(at_work_seconds) + 1
        $("div.time-runner").html(secondsToDuration(at_work_seconds));
        $("title").html(` ${whiteLabelCompany} | ` + secondsToDuration(at_work_seconds));
    }, 1000);
}
