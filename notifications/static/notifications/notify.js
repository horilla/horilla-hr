var notify_badge_class;
var notify_menu_class;
var notify_api_url;
var notify_fetch_count;
var notify_unread_url;
var notify_mark_all_unread_url;
var notify_refresh_period = 15000;
// Set notify_mark_as_read to true to mark notifications as read when fetched
var notify_mark_as_read = false;
var consecutive_misfires = 0;
var registered_functions = [];
// Single handle for the poll chain. Every reschedule goes through
// schedule_next() so an out-of-band call (visibilitychange) replaces the
// pending timer instead of starting a second, parallel chain.
var notify_poll_timer = null;

function fill_notification_badge(data) {
    var badges = document.getElementsByClassName(notify_badge_class);
    if (badges) {
        for (var i = 0; i < badges.length; i++) {
            badges[i].innerHTML = data.unread_count;
        }
    }
}

function fill_notification_list(data) {
    var menus = document.getElementsByClassName(notify_menu_class);
    if (menus) {
        var messages = data.unread_list.map(function (item) {
            var message = "";

            if (typeof item.actor !== 'undefined') {
                message = item.actor;
            }
            if (typeof item.verb !== 'undefined') {
                message = message + " " + item.verb;
            }
            if (typeof item.target !== 'undefined') {
                message = message + " " + item.target;
            }
            if (typeof item.timestamp !== 'undefined') {
                message = message + " " + item.timestamp;
            }
            return '<li>' + message + '</li>';
        }).join('')

        for (var i = 0; i < menus.length; i++) {
            menus[i].innerHTML = messages;
        }
    }
}

function register_notifier(func) {
    registered_functions.push(func);
}

function schedule_next() {
    if (notify_poll_timer !== null) {
        clearTimeout(notify_poll_timer);
    }
    notify_poll_timer = setTimeout(fetch_api_data, notify_refresh_period);
}

function fetch_api_data() {
    // Skip the request while the tab is hidden, but keep the timer running so
    // polling resumes on its own. An unattended tab otherwise keeps hitting
    // this endpoint indefinitely: wasted server work everywhere, and on
    // per-second-billed hosting it reads as real traffic and stops the
    // container ever scaling to zero. document.hidden is guarded so very old
    // browsers keep the previous always-poll behaviour.
    if (typeof document !== "undefined" && document.hidden === true) {
        schedule_next();
        return;
    }
    // only fetch data if a function is setup
    if (registered_functions.length > 0) {
        var r = new XMLHttpRequest();
        var params = '?max=' + notify_fetch_count;

        if (notify_mark_as_read) {
            params += '&mark_as_read=true';
        }

        r.addEventListener('readystatechange', function (event) {
            if (this.readyState === 4) {
                if (this.status === 200) {
                    consecutive_misfires = 0;
                    var data = JSON.parse(r.responseText);
                    for (var i = 0; i < registered_functions.length; i++) {
                        registered_functions[i](data);
                    }
                } else {
                    consecutive_misfires++;
                }
            }
        });
        r.open("GET", notify_api_url + params, true);
        r.send();
    }
    if (consecutive_misfires < 10) {
        schedule_next();
    } else {
        var badges = document.getElementsByClassName(notify_badge_class);
        if (badges) {
            for (var i = 0; i < badges.length; i++) {
                badges[i].innerHTML = "!";
                badges[i].title = "Connection lost!"
            }
        }
    }
}

// Refresh as soon as the tab is focused again, so a returning user sees the
// current count instead of waiting out the remainder of the interval.
if (typeof document !== "undefined" && document.addEventListener) {
    document.addEventListener("visibilitychange", function () {
        if (document.hidden === false && registered_functions.length > 0) {
            // Replaces the pending timer rather than adding to it.
            fetch_api_data();
        }
    });
}

notify_poll_timer = setTimeout(fetch_api_data, 1000);
