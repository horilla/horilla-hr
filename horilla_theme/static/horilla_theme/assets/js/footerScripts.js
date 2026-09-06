$(function () {
    $(document).tooltip({
        position: {
            my: "right top+8",
            at: "right bottom",
            collision: "flipfit"
        }
    });
});

Toast = Swal.mixin({
    toast: true,
    icon: "success",
    title: "General Title",
    animation: true,
    position: "top-right",
    showConfirmButton: false,
    timer: 3000,
    timerProgressBar: true,
    didOpen: (toast) => {
        toast.addEventListener("mouseenter", Swal.stopTimer);
        toast.addEventListener("mouseleave", Swal.resumeTimer);
    },
});

async function loadComponent(elementId, path) {
    try {
        const response = await fetch(path);
        const html = await response.text();
        document.getElementById(elementId).innerHTML = html;
    } catch (error) {
        console.error("Error loading component:", error);
    }
}

// Gender Chart

// document.addEventListener("DOMContentLoaded", () => {
//     const ctx = document.getElementById("genderChart").getContext("2d");

//     // Load image only once
//     const centerImage = new Image();
//     centerImage.src = "/static/horilla_theme/assets/img/icons/gender.svg";

//     new Chart(ctx, {
//         type: "doughnut",
//         data: {
//             labels: ["Male", "Female", "Others"],
//             datasets: [
//                 {
//                     data: [35, 55, 10],
//                     backgroundColor: ["#cfe9ff", "#ffc9de", "#e6ccff"],
//                     borderWidth: 0,
//                 },
//             ],
//         },
//         options: {
//             cutout: "70%",
//             responsive: true,
//             maintainAspectRatio: false,
//             plugins: {
//                 legend: {
//                     position: "bottom",
//                     labels: {
//                         usePointStyle: true,
//                         pointStyle: "circle",
//                         padding: 20,
//                         font: {
//                             size: 12,
//                         },
//                         color: "#000",
//                     },
//                 },
//             },
//         },
//         plugins: [
//             {
//                 id: "centerIcon",
//                 afterDraw(chart) {
//                     if (!centerImage.complete) return; // Wait till image is loaded
//                     const ctx = chart.ctx;
//                     const size = 70;
//                     ctx.drawImage(
//                         centerImage,
//                         chart.width / 2 - size / 2,
//                         chart.height / 2 - size / 2 - 20,
//                         size,
//                         size
//                     );
//                 },
//             },
//         ],
//     });
// });

// Department chart

// document.addEventListener("DOMContentLoaded", () => {
//     const ctx = document
//         .getElementById("departmentChart")
//         .getContext("2d");

//     const departmentLabels = [
//         "Sales Dept",
//         "IT Dept",
//         "DM Dept",
//         "SEO Dept",
//         "Odoo Dept",
//         "Horilla Dept",
//     ];

//     const departmentColors = [
//         "#facc15",
//         "#f87171",
//         "#ddd6fe",
//         "#a5b4fc",
//         "#93c5fd",
//         "#d1d5db",
//     ];

//     const departmentValues = [1000, 800, 900, 1100, 2000, 1070];

//     const visibility = Array(departmentLabels.length).fill(true);

//     const departmentChart = new Chart(ctx, {
//         type: "doughnut",
//         data: {
//             labels: departmentLabels,
//             datasets: [
//                 {
//                     data: departmentValues,
//                     backgroundColor: departmentColors,
//                     borderWidth: 0,
//                     borderRadius: 10,
//                     hoverOffset: 8,
//                 },
//             ],
//         },
//         options: {
//             cutout: "70%",
//             responsive: true,
//             maintainAspectRatio: false,
//             plugins: {
//                 legend: { display: false },
//                 tooltip: {
//                     backgroundColor: "#111827",
//                     bodyColor: "#f3f4f6",
//                     borderColor: "#e5e7eb",
//                     borderWidth: 1,
//                 },
//             },
//         },
//         plugins: [
//             {
//                 id: "centerText",
//                 afterDraw(chart) {
//                     const { width, height, ctx } = chart;
//                     ctx.save();

//                     const total =
//                         chart.data.datasets[0].data.reduce(
//                             (sum, val) => sum + val,
//                             0
//                         );

//                     ctx.font = "bold 22px sans-serif";
//                     ctx.fillStyle = "#374151";
//                     ctx.textAlign = "center";
//                     ctx.textBaseline = "middle";
//                     ctx.fillText(total, width / 2, height / 2 - 5);

//                     ctx.font = "15px sans-serif";
//                     ctx.fillStyle = "#9ca3af";
//                     ctx.fillText(
//                         "Total",
//                         width / 2,
//                         height / 2 + 20
//                     );

//                     ctx.restore();
//                 },
//             },
//         ],
//     });

//     // Make custom legend items clickable
//     const legendItems =
//         document.querySelectorAll("#chartLegend > div");

//     legendItems.forEach((item, index) => {
//         item.style.cursor = "pointer";

//         item.addEventListener("click", () => {
//             visibility[index] = !visibility[index];

//             // Update chart dataset
//             departmentChart.data.datasets[0].data =
//                 departmentValues.map((val, i) =>
//                     visibility[i] ? val : 0
//                 );

//             // Dim legend dot and strike-through label
//             const span = item.querySelector("span");
//             if (visibility[index]) {
//                 span.style.opacity = "1";
//                 item.style.textDecoration = "none";
//             } else {
//                 span.style.opacity = "0.4";
//                 item.style.textDecoration = "line-through";
//             }

//             departmentChart.update();
//         });
//     });
// });

// Onboarding Chart

// document.addEventListener("DOMContentLoaded", () => {
//     const ctx = document.getElementById("recruitmentChart").getContext("2d");

//     const labels = [
//         "Recruitment drive",
//         "Future force recruitment",
//         "Administrative assistant",
//     ];
//     const colors = ["#a5b4fc", "#fca5a5", "#fdba74"];
//     const dataValues = [35, 45, 38];
//     const visibility = [true, true, true];

//     const chart = new Chart(ctx, {
//         type: "bar",
//         data: {
//             labels: labels,
//             datasets: [
//                 {
//                     label: "Recruitment Count",
//                     data: dataValues,
//                     backgroundColor: colors,
//                     borderRadius: 20,
//                     barPercentage: 0.6,
//                     categoryPercentage: 0.6,
//                 },
//             ],
//         },
//         options: {
//             responsive: true,
//             maintainAspectRatio: false,
//             plugins: {
//                 legend: { display: false },
//                 tooltip: { enabled: true },
//             },
//             scales: {
//                 y: {
//                     beginAtZero: true,
//                     max: 100,
//                     ticks: { stepSize: 20 },
//                     grid: { drawBorder: false, color: "#e5e7eb" },
//                 },
//                 x: {
//                     ticks: { display: false },
//                     grid: { display: false },
//                     border: { display: true, color: "#d1d5db" },
//                 },
//             },
//         },
//     });

//     // Create clickable legend dynamically
//     const legendContainer = document.getElementById("recruitmentLegend");
//     labels.forEach((label, i) => {
//         const item = document.createElement("div");
//         item.className = "flex items-center gap-2 cursor-pointer";
//         item.innerHTML = `
//       <span class="w-4 h-4 rounded-full inline-block" style="background:${colors[i]}; transition: 0.3s;"></span>
//       <span>${label}</span>
//     `;
//         item.addEventListener("click", () => {
//             visibility[i] = !visibility[i];

//             // Update data & bar color
//             chart.data.datasets[0].data = dataValues.map((val, index) =>
//                 visibility[index] ? val : 0
//             );
//             chart.data.datasets[0].backgroundColor = colors.map(
//                 (color, index) => (visibility[index] ? color : "#e5e7eb")
//             );
//             chart.update();

//             // Update legend visuals
//             const dot = item.querySelector("span");
//             const text = item.querySelectorAll("span")[1];
//             dot.style.opacity = visibility[i] ? "1" : "0.4";
//             text.style.textDecoration = visibility[i] ? "none" : "line-through";
//         });

//         legendContainer.appendChild(item);
//     });
// });

// Recruitment Chart

// document.addEventListener("DOMContentLoaded", () => {
//     const ctx = document
//         .getElementById("recruitmentFlowChart")
//         .getContext("2d");

//     new Chart(ctx, {
//         type: "bar",
//         data: {
//             labels: [
//                 "Initial",
//                 "Applied",
//                 "Test",
//                 "Interview",
//                 "Cancelled",
//                 "Hired",
//             ],
//             datasets: [
//                 {
//                     label: "Recruitment Drive",
//                     data: [55, 35, 0, 0, 28, 90],
//                     backgroundColor: "#a5b4fc",
//                     borderRadius: 10,
//                     barPercentage: 0.8,
//                     categoryPercentage: 0.6,
//                 },
//                 {
//                     label: "Future Force Recruitment",
//                     data: [0, 15, 0, 0, 0, 65],
//                     backgroundColor: "#fca5a5",
//                     borderRadius: 10,
//                     barPercentage: 0.8,
//                     categoryPercentage: 0.6,
//                 },
//                 {
//                     label: "Administrative Assistant",
//                     data: [0, 0, 0, 0, 0, 15],
//                     backgroundColor: "#fdba74",
//                     borderRadius: 10,
//                     barPercentage: 0.8,
//                     categoryPercentage: 0.6,
//                 },
//             ],
//         },
//         options: {
//             responsive: true,
//             maintainAspectRatio: false,
//             scales: {
//                 y: {
//                     beginAtZero: true,
//                     ticks: {
//                         stepSize: 20,
//                         color: "#6b7280",
//                     },
//                     grid: {
//                         color: "#e5e7eb",
//                     },
//                 },
//                 x: {
//                     ticks: {
//                         color: "#6b7280",
//                     },
//                     grid: {
//                         display: false,
//                     },
//                 },
//             },
//             plugins: {
//                 legend: {
//                     position: "bottom",
//                     labels: {
//                         usePointStyle: true,
//                         pointStyle: "circle",
//                         font: {
//                             size: 12,
//                         },
//                         color: "#374151",
//                         padding: 15,
//                     },
//                 },
//                 tooltip: {
//                     enabled: true,
//                 },
//             },
//         },
//     });
// });


// document.addEventListener("DOMContentLoaded", () => {
//     const ctx = document.getElementById("hiredChart").getContext("2d");

//     const labels = [
//         "Recruitment drive",
//         "Future force recruitment",
//         "Administrative assistant",
//     ];
//     const colors = ["#a5b4fc", "#fca5a5", "#fdba74"];
//     const values = [35, 45, 38];
//     const visibility = [true, true, true];

//     const chart = new Chart(ctx, {
//         type: "bar",
//         data: {
//             labels: labels,
//             datasets: [
//                 {
//                     label: "Recruitment Count",
//                     data: values,
//                     backgroundColor: colors,
//                     borderRadius: 20,
//                     barPercentage: 0.6,
//                     categoryPercentage: 0.6,
//                 },
//             ],
//         },
//         options: {
//             responsive: true,
//             maintainAspectRatio: false,
//             plugins: {
//                 legend: { display: false },
//                 tooltip: { enabled: true },
//             },
//             scales: {
//                 y: {
//                     beginAtZero: true,
//                     max: 100,
//                     ticks: { stepSize: 20 },
//                     grid: { drawBorder: false, color: "#e5e7eb" },
//                 },
//                 x: {
//                     ticks: { display: false },
//                     grid: { display: false },
//                     border: { display: true, color: "#d1d5db" },
//                 },
//             },
//         },
//     });

//     // Toggle bars and strike text
//     const legendItems = document.querySelectorAll("#hiredLegend > div");
//     legendItems.forEach((item, i) => {
//         item.addEventListener("click", () => {
//             visibility[i] = !visibility[i];

//             // Update chart data
//             chart.data.datasets[0].data = values.map((val, index) =>
//                 visibility[index] ? val : 0
//             );
//             chart.data.datasets[0].backgroundColor = colors.map((col, index) =>
//                 visibility[index] ? col : "#e5e7eb"
//             );
//             chart.update();

//             // Update legend visuals
//             const dot = item.querySelectorAll("span")[0];
//             const text = item.querySelectorAll("span")[1];

//             dot.style.opacity = visibility[i] ? "1" : "0.4";
//             text.style.textDecoration = visibility[i] ? "none" : "line-through";
//         });
//     });
// });

function validateFile(element, fileTarget, reload = false) {
    var fileInput = document.getElementById(fileTarget);
    var filePath = fileInput.value;
    var allowedExtensions = /(\.xlsx|\.csv)$/i;

    if (!allowedExtensions.exec(filePath)) {
        Swal.fire({
            icon: "error",
            title: "Invalid File",
            text: "Please upload a valid XLSX file.",
            customClass: {
                popup: "file-xlsx-validation",
            },
        }).then((result) => {
            if (result.isConfirmed && reload) {
                $(".oh-modal--show").removeClass("oh-modal--show");
                window.location.reload();
            }
        });
        fileInput.value = "";
        return false;
    }
    $(this).closest("form").submit();
}

function initSidebarToggle() {
    // Reusable Sidebar Toggle
    document.querySelectorAll(".toggleSidemenu").forEach((button) => {
        button.addEventListener("click", () => {
            const sidebarId = button.getAttribute("data-sidebar");
            const sidebar = document.getElementById(sidebarId);
            if (sidebar) {
                sidebar.classList.toggle("active");
                document.body.classList.toggle("overflow-hidden");
            }
        });
    });

    document.querySelectorAll(".closeSidemenu").forEach((button) => {
        button.addEventListener("click", () => {
            const sidebarId = button.getAttribute("data-sidebar");
            const sidebar = document.getElementById(sidebarId);
            if (sidebar) {
                sidebar.classList.remove("active");
                document.body.classList.remove("overflow-hidden");
            }
        });
    });
}

function switchTab(e) {
    let parentContainerEl = e.target.closest(".oh-tabs");
    let tabElement = e.target.closest(".oh-tabs__tab");
    let targetSelector = e.target.dataset.target;
    let targetEl = parentContainerEl
        ? parentContainerEl.querySelector(targetSelector)
        : null;

    // Highlight active tabs
    if (tabElement && !tabElement.classList.contains("oh-tabs__tab--active")) {
        parentContainerEl
            .querySelectorAll(".oh-tabs__tab--active")
            .forEach(function (item) {
                item.classList.remove("oh-tabs__tab--active");
            });

        if (!tabElement.classList.contains("oh-tabs__new-tab")) {
            tabElement.classList.add("oh-tabs__tab--active");
        }
    }

    // Switch tabs
    if (targetEl && !targetEl.classList.contains("oh-tabs__content--active")) {
        parentContainerEl
            .querySelectorAll(".oh-tabs__content--active")
            .forEach(function (item) {
                item.classList.remove("oh-tabs__content--active");
            });
        targetEl.classList.add("oh-tabs__content--active");
    }
}

function setAccordionFoldIcon(icon, isOpen) {
    if (!icon) {
        return;
    }
    // Match recruitment pipeline fold icons: open = up, closed = down.
    if (icon.tagName && icon.tagName.toLowerCase() === "ion-icon") {
        icon.setAttribute(
            "name",
            isOpen ? "chevron-up-outline" : "chevron-down-outline"
        );
        return;
    }
    icon.textContent = isOpen ? "−" : "+";
}

function toggleAccordion(btn) {

    //  * This function is intended to be called explicitly via `hx-on:click` in HTMX-rendered content,
    const panel = btn.nextElementSibling;
    const icon = btn.querySelector(".icon");
    const isOpen = panel.style.maxHeight && panel.style.maxHeight !== "0px";

    // Toggle current panel
    if (!isOpen) {
        // Content for this panel arrives async via htmx (hx-get/hx-target),
        // so the real height isn't known yet. Grow to the existing (likely
        // empty) scrollHeight now for an instant response, then the
        // htmx:afterSwap listener below re-measures once content lands —
        // avoids animating to/from an arbitrary fixed height that doesn't
        // match the content, which read as janky/laggy.
        panel.style.maxHeight = panel.scrollHeight + "px";
        setAccordionFoldIcon(icon, true);
        // btn.classList.remove("bg-primary-100", "text-primary-600");
        // btn.classList.add("bg-primary-600", "text-white");
    } else {
        panel.style.maxHeight = null;
        setAccordionFoldIcon(icon, false);
        // btn.classList.remove("bg-primary-600", "text-white");
        // btn.classList.add("bg-primary-100", "text-primary-600");
    }
}

// The "Customize columns" popover (.oh-column-config, opened via
// .is-column-config-trigger) is positioned with a fixed `top` offset below
// its trigger and a CSS max-height based only on total viewport height --
// it has no idea how much space is actually left below the trigger, so on
// a short viewport (or a trigger sitting low on the page) its lower portion
// renders past the viewport edge instead of flipping up or shrinking to fit.
function positionColumnConfigPopover(trigger) {
    var popover = trigger.closest(".relative")?.querySelector(".oh-sticky-table_dropdown");
    if (!popover) {
        return;
    }

    var margin = 12;
    var minHeight = 150;
    var triggerRect = trigger.getBoundingClientRect();
    var viewportHeight = window.innerHeight;
    var viewportWidth = window.innerWidth;
    var spaceBelow = viewportHeight - triggerRect.bottom - margin;
    var spaceAbove = triggerRect.top - margin;
    var popoverWidth = popover.offsetWidth || 280;

    // Measure the popover's own natural content height (unclamped) before
    // deciding anything -- a previous open may have left an inline
    // max-height from clamping, which would make scrollHeight measure the
    // clamped box instead of the real content.
    var previousMaxHeight = popover.style.maxHeight;
    popover.style.maxHeight = "none";
    var desiredHeight = Math.min(420, popover.scrollHeight);
    popover.style.maxHeight = previousMaxHeight;

    popover.style.position = "fixed";
    popover.style.right = "auto";
    popover.style.left =
        Math.max(
            margin,
            Math.min(triggerRect.right - popoverWidth, viewportWidth - popoverWidth - margin)
        ) + "px";

    // Prefer whichever side can show the popover at its full natural
    // height. Only when NEITHER side has enough room do we fall back to
    // the side with more space and clamp to it (the column list's own
    // overflow-y: auto then keeps the rest reachable by scrolling).
    var openUpward =
        spaceBelow < desiredHeight && (spaceAbove >= desiredHeight || spaceAbove > spaceBelow);

    if (openUpward) {
        popover.style.top = "auto";
        popover.style.bottom = viewportHeight - triggerRect.top + 8 + "px";
        popover.style.maxHeight = Math.max(minHeight, Math.min(desiredHeight, spaceAbove)) + "px";
    } else {
        popover.style.bottom = "auto";
        popover.style.top = triggerRect.bottom + 8 + "px";
        popover.style.maxHeight = Math.max(minHeight, Math.min(desiredHeight, spaceBelow)) + "px";
    }
}

// Delegated + capture phase: the trigger button's own onclick calls
// event.stopPropagation(), which would otherwise stop a bubble-phase
// document listener from ever seeing this click; capture fires before that.
// Alpine's own x-show toggle (bound on the same button, runs after this
// capture-phase code) isn't guaranteed to have flushed the popover's
// display style by the next animation frame, so rather than guess at
// Alpine's update timing, a MutationObserver reacts to the style attribute
// actually changing and positions the popover exactly when it becomes
// visible -- and keeps doing so for every subsequent open/close on the
// same popover (e.g. after a window resize between opens).
document.addEventListener(
    "click",
    function (event) {
        var trigger = event.target.closest(".is-column-config-trigger");
        if (!trigger) {
            return;
        }
        var popover = trigger.closest(".relative")?.querySelector(".oh-sticky-table_dropdown");
        if (!popover || popover.dataset.columnConfigObserved) {
            return;
        }
        popover.dataset.columnConfigObserved = "true";
        // positionColumnConfigPopover writes to this same element's style
        // attribute, which the observer also watches -- disconnect before
        // writing and reconnect after, or every self-triggered write would
        // queue another callback (an infinite loop that hangs the page).
        var observer = new MutationObserver(function () {
            if (getComputedStyle(popover).display === "none") {
                return;
            }
            observer.disconnect();
            positionColumnConfigPopover(trigger);
            observer.observe(popover, { attributes: true, attributeFilter: ["style", "class"] });
        });
        observer.observe(popover, { attributes: true, attributeFilter: ["style", "class"] });
    },
    true
);

// Re-measure an accordion panel once its async content has actually
// landed, so the open transition smoothly grows to the real content
// height instead of a stale/guessed one.
document.body.addEventListener("htmx:afterSwap", function (evt) {
    const panel = evt.target;
    if (panel && panel.classList && panel.classList.contains("accordion-panel")) {
        panel.style.maxHeight = panel.scrollHeight + "px";
    }
});

document.querySelectorAll('.accordion-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
        const panel = btn.nextElementSibling;
        const icon = btn.querySelector('.icon');
        const isOpen = panel.style.maxHeight && panel.style.maxHeight !== "0px";

        // Toggle current
        if (!isOpen) {
            panel.style.maxHeight = panel.scrollHeight + 'px';
            setAccordionFoldIcon(icon, true);
            // btn.classList.remove("bg-primary-100", "text-primary-600");
            // btn.classList.add("bg-primary-600", "text-white");
        } else {
            panel.style.maxHeight = null;
            setAccordionFoldIcon(icon, false);
            // btn.classList.remove("bg-primary-600", "text-white");
            // btn.classList.add("bg-primary-100", "text-primary-600");
        }
    });
});

$(document).on("htmx:afterSettle", function (event) {
    // $(".dropdown-toggle").on("click", function () {
    //     const dropdownMenu = $(this).next(".dropdown-menu");
    //     const isOpen = dropdownMenu.is(":visible");

    //     $(".dropdown-menu").not(dropdownMenu).hide();

    //     if (isOpen) {
    //         dropdownMenu.hide();
    //     } else {
    //         dropdownMenu.show();
    //     }
    // });

    // method for sticky issue -- scoped to the subtree htmx actually just
    // swapped (event.target), not the whole document. This handler fires on
    // EVERY htmx swap anywhere on the page (e.g. opening the Edit modal into
    // #genericModalBody), and an unscoped $(".oh-permission-table--toggle")
    // would re-collapse every accordion row on the page each time, undoing
    // whatever the user had just expanded.
    const $scope = $(event.target);
    const $fixedTable = $scope.find('.fixed-table').addBack('.fixed-table');
    if ($fixedTable.length === 0) return;

    const bulk_select_option = $fixedTable.data('bulk-select-option');
    if (bulk_select_option) {
        $scope.find('tr').each(function () {
            const $cells = $(this).find('th, td');
            if ($cells.length > 0) {
                $cells.eq(0).addClass('stickyleft');
                $cells.eq(1).addClass('stickyleft-second');
            }
        });
    } else {
        $scope.find('tr').each(function () {
            const $cells = $(this).find('th, td');
            if ($cells.length > 0) {
                $cells.eq(0).addClass('stickyleft');
            }
        });
    };

    const $toggles = $scope.find(".oh-permission-table--toggle");
    if ($toggles.length > 0) {
        $toggles.each(function () {
            $(this).closest("tr").addClass("oh-permission-table--collapsed")
        });
    }
});

$(".oh-password-input--toggle").on("click", function (e) {
    e.preventDefault();

    const $toggle = $(this);
    const $passwordInput = $toggle.siblings(".oh-input--password");
    const $showIcon = $toggle.find(".oh-password-input__show-icon");
    const $hideIcon = $toggle.find(".oh-password-input__hide-icon");

    if ($passwordInput.attr("type") === "password") {
        $passwordInput.attr("type", "text");
        $showIcon.addClass("hidden");
        $hideIcon.removeClass("hidden");
    } else {
        $passwordInput.attr("type", "password");
        $showIcon.removeClass("hidden");
        $hideIcon.addClass("hidden");
    }
});

$(".oh-modal__close").on("click", function () {
    $(this).closest(".oh-modal--show").removeClass("oh-modal--show")
})

$(document).on("click", ".oh-accordion-header", function (event) {
    event.stopImmediatePropagation();
    var $accordion = $(this).closest(".oh-accordion");
    $accordion.toggleClass("oh-accordion--show");
    var icon = this.querySelector("ion-icon.icon");
    if (icon) {
        icon.setAttribute(
            "name",
            $accordion.hasClass("oh-accordion--show") ? "chevron-up-outline" : "chevron-down-outline"
        );
    }
});

var avatarPreviewTimer = null;

$(document).on("mouseenter", ".avatar-thumb", function (e) {
    var $thumb = $(this);
    var src = $thumb.data("src");

    avatarPreviewTimer = setTimeout(function () {
        var thumbWidth = $thumb[0].offsetWidth;
        var thumbHeight = $thumb[0].offsetHeight;

        $("#previewImg")
            .attr("src", src)
            .css({
                width: thumbWidth * 5 + "px",
                height: thumbHeight * 5 + "px",
                boxShadow: "0 10px 20px rgba(0,0,0,0.3)",
                background: "white"
            });

        $("#imagePreview")
            .css({
                top: e.pageY + 15 + "px",
                left: e.pageX + 15 + "px"
            })
            .show();
    }, 300);
});

// Mouse move
$(document).on("mousemove", ".avatar-thumb", function (e) {
    $("#imagePreview").css({
        top: e.pageY + 15 + "px",
        left: e.pageX + 15 + "px"
    });
});

// Mouse leave
$(document).on("mouseleave", ".avatar-thumb", function () {
    clearTimeout(avatarPreviewTimer);
    $("#imagePreview").hide();
});
