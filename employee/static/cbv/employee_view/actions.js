
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
        const cookies = document.cookie.split(";");
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) === name + "=") {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function reloadEmployeeListContainer() {
    var applyBtn = document.getElementById("applyFilter");
    if (applyBtn && window.htmx) {
        applyBtn.click();
        if (typeof jQuery !== "undefined" && $("#reloadMessagesButton").length) {
            $("#reloadMessagesButton").click();
        }
        return;
    }
    var form = document.getElementById("filterForm");
    if (form && window.htmx) {
        htmx.trigger(form, "submit");
        if (typeof jQuery !== "undefined" && $("#reloadMessagesButton").length) {
            $("#reloadMessagesButton").click();
        }
        return;
    }
    window.location.reload();
}


var form = document.getElementById("workInfoImportForm");

// Add an event listener to the form submission
form.addEventListener("submit", function (event) {
    // Prevent the default form submission
    event.preventDefault();

    // Create a new form data object
    $(".oh-dropdown__import-form").css("display", "none");
    $("#uploading").css("display", "block");
    var formData = new FormData();

    // Append the file to the form data object
    var fileInput = document.querySelector("#workInfoImportFile");
    formData.append("file", fileInput.files[0]);
    $.ajax({
        type: "POST",
        url: "/employee/work-info-import/",
        dataType: "binary",
        data: formData,
        processData: false,
        contentType: false,
        headers: {
            "X-CSRFToken": getCookie("csrftoken"),
        },
        xhrFields: {
            responseType: "blob",
        },
        success: function (response, textStatus, xhr) {
            var errorCount = xhr.getResponseHeader('X-Error-Count');
            if (typeof response === 'object' && response.type == 'application/json') {
                var reader = new FileReader();

                reader.onload = function () {
                    var json = JSON.parse(reader.result);

                    if (json.success_count > 0) {
                        Swal.fire({
                            text: json.success_count + " " + gettext("Employees Imported Successfully"),
                            icon: "success",
                            showConfirmButton: false,
                            timer: 3000,
                            timerProgressBar: true,
                        }).then(function () {
                            window.location.reload();
                        });
                    }
                }
                reader.readAsText(response);
                return;
            }
            if (!$(".file-xlsx-validation").length) {
                swal.fire({
                    text: gettext("You have") + " " + errorCount + " " + gettext("errors. Do you want to download the error list?"),
                    icon: "error",
                    showCancelButton: true,
                    showDenyButton: true,
                    confirmButtonText: gettext("Download error list & Skip Import"),
                    denyButtonText: gettext("Download error list & Continue Import"),
                    cancelButtonText: i18nMessages.cancel,
                    confirmButtonColor: "#008000",
                    denyButtonColor: "#6c757d",
                    customClass: {
                        container: 'custom-swal-container'
                    }
                })
                    .then((result) => {
                        if (result.isConfirmed) {
                            const file = new Blob([response], {
                                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            });
                            const url = URL.createObjectURL(file);
                            const link = document.createElement("a");
                            link.href = url;
                            link.download = "ImportError.xlsx";
                            document.body.appendChild(link);
                            link.click();
                            window.location.reload();
                        }
                        else if (result.isDenied) {
                            formData.append("create_work_info", true);
                            $.ajax({
                                type: "POST",
                                url: "/employee/work-info-import/",
                                dataType: "binary",
                                data: formData,
                                processData: false,
                                contentType: false,
                                headers: {
                                    "X-CSRFToken": getCookie("csrftoken"),
                                },
                                xhrFields: {
                                    responseType: "blob",
                                },
                                success: function (response, textStatus, xhr) {
                                    Swal.fire({
                                        text: gettext("Employees Imported Successfully"),
                                        icon: "success",
                                        showConfirmButton: false,
                                        timer: 3000,
                                        timerProgressBar: true,
                                    }).then(function () {
                                        const file = new Blob([response], {
                                            type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                        });
                                        const url = URL.createObjectURL(file);
                                        const link = document.createElement("a");
                                        link.href = url;
                                        link.download = "ImportError.xlsx";
                                        document.body.appendChild(link);
                                        link.click();
                                        window.location.reload();
                                    });

                                    return;
                                }
                            })
                        }
                        else {
                            $(".oh-dropdown__import-form").css("display", "block");
                            $("#uploading").css("display", "none");
                        }
                    });
            }

        },
        error: function (xhr, textStatus, errorThrown) {
            console.error("Error downloading file:", errorThrown);
        },
    });
});



$(document).on("click", "#work-info-import", function (e) {
    e.preventDefault();

    Swal.fire({
        text: i18nMessages.downloadTemplate,
        icon: "question",
        showCancelButton: true,
        confirmButtonColor: "#008000",
        cancelButtonColor: "#6c757d",
        confirmButtonText: i18nMessages.confirm,
        cancelButtonText: i18nMessages.cancel,
    }).then(function (result) {
        if (result.isConfirmed) {
            $("#loading").show();

            var xhr = new XMLHttpRequest();
            xhr.open("GET", "/employee/work-info-import", true);
            xhr.responseType = "arraybuffer";

            xhr.upload.onprogress = function (e) {
                if (e.lengthComputable) {
                    var percent = (e.loaded / e.total) * 100;
                    $(".progress-bar")
                        .width(percent + "%")
                        .attr("aria-valuenow", percent);
                    $("#progress-text").text(
                        i18nMessages.uploading + percent.toFixed(2) + "%"
                    );
                }
            };

            xhr.onload = function (e) {
                if (this.status == 200) {
                    const file = new Blob([this.response], {
                        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    });
                    const url = URL.createObjectURL(file);
                    const link = document.createElement("a");
                    link.href = url;
                    link.download = "work_info_template.xlsx";
                    document.body.appendChild(link);
                    link.click();
                }
            };


            xhr.onerror = function () {
                console.error("Error downloading file:", xhr.statusText);
            };

            xhr.onerror = function (e) {
                console.error("Error downloading file:", e);
            };
            xhr.send();
        }
    });

});
$(document).ajaxStart(function () {
    $("#loading").show();
});

$(document).ajaxStop(function () {
    $("#loading").hide();
});

function simulateProgress() {

    let progressBar = document.querySelector(".progress-bar");
    let progressText = document.getElementById("progress-text");

    let width = 0;
    let interval = setInterval(function () {
        if (width >= 100) {
            clearInterval(interval);
            progressText.innerText = uploadMessage;
            setTimeout(function () {
                document.getElementById("loading").style.display = "none";
            }, 3000);
            Swal.fire({
                text: importMessage,
                icon: "success",
                showConfirmButton: false,
                timer: 2000,
                timerProgressBar: true,
            });
            setTimeout(function () {
                $("#workInfoImport").removeClass("oh-modal--show");
                location.reload(true);
            }, 2000);
        } else {
            width++;
            progressBar.style.width = width + "%";
            progressBar.setAttribute("aria-valuenow", width);
            progressText.innerText = i18nMessages.uploading + width + "%";
        }
    }, 20);

}



$(document).on("click", "#archiveEmployees", function (e) {
    e.preventDefault();
    ids = [];
    ids.push($("#selectedInstances").attr("data-ids"));
    ids = JSON.parse($("#selectedInstances").attr("data-ids"));
    if (ids.length === 0) {
        Swal.fire({
            text: i18nMessages.noRowsSelected,
            icon: "warning",
            confirmButtonText: i18nMessages.close,
        });
    } else {
        Swal.fire({
            text: i18nMessages.confirmBulkArchive,
            icon: "info",
            showCancelButton: true,
            confirmButtonColor: "#d33",
            cancelButtonColor: "#6c757d",
            confirmButtonText: i18nMessages.confirm,
            cancelButtonText: i18nMessages.cancel,
        }).then(function (result) {
            if (result.isConfirmed) {
                e.preventDefault();
                ids = [];
                ids.push($("#selectedInstances").attr("data-ids"));
                ids = JSON.parse($("#selectedInstances").attr("data-ids"));
                $.ajax({
                    type: "POST",
                    url: "/employee/employee-bulk-archive/?is_active=False",
                    data: {
                        csrfmiddlewaretoken: getCookie("csrftoken"),
                        ids: JSON.stringify(ids),
                    },
                    success: function (response, textStatus, jqXHR) {
                        if (jqXHR.status === 200) {
                            reloadEmployeeListContainer();
                        } else {
                            // console.log("Unexpected HTTP status:", jqXHR.status);
                        }
                    },
                });
            }
        });
    }
});


$(document).on("click", "#unArchiveEmployees", function (e) {
    e.preventDefault();

    ids = [];
    ids.push($("#selectedInstances").attr("data-ids"));
    ids = JSON.parse($("#selectedInstances").attr("data-ids"));
    if (ids.length === 0) {
        Swal.fire({
            text: i18nMessages.noRowsSelected,
            icon: "warning",
            confirmButtonText: i18nMessages.close,
        });
    } else {
        Swal.fire({
            text: i18nMessages.confirmBulkUnArchive,
            icon: "info",
            showCancelButton: true,
            confirmButtonColor: "#008000",
            cancelButtonColor: "#6c757d",
            confirmButtonText: i18nMessages.confirm,
            cancelButtonText: i18nMessages.cancel,
        }).then(function (result) {
            if (result.isConfirmed) {
                e.preventDefault();

                ids = [];

                ids.push($("#selectedInstances").attr("data-ids"));
                ids = JSON.parse($("#selectedInstances").attr("data-ids"));

                $.ajax({
                    type: "POST",
                    url: "/employee/employee-bulk-archive/?is_active=True",
                    data: {
                        csrfmiddlewaretoken: getCookie("csrftoken"),
                        ids: JSON.stringify(ids),
                    },
                    success: function (response, textStatus, jqXHR) {
                        if (jqXHR.status === 200) {
                            reloadEmployeeListContainer();
                        } else {
                            // console.log("Unexpected HTTP status:", jqXHR.status);
                        }
                    },
                });
            }
        });
    }
});

$(document).on("click", "#resetPasswordEmployees", function (e) {
    e.preventDefault();
    ids = [];
    ids.push($("#selectedInstances").attr("data-ids"));
    ids = JSON.parse($("#selectedInstances").attr("data-ids"));
    if (ids.length === 0) {
        Swal.fire({
            text: i18nMessages.noRowsSelected,
            icon: "warning",
            confirmButtonText: i18nMessages.close,
        });
    } else {
        Swal.fire({
            text: i18nMessages.confirmBulkResetPassword,
            icon: "warning",
            showCancelButton: true,
            confirmButtonColor: "#d33",
            cancelButtonColor: "#6c757d",
            confirmButtonText: i18nMessages.confirm,
            cancelButtonText: i18nMessages.cancel,
        }).then(function (result) {
            if (result.isConfirmed) {
                ids = [];
                ids.push($("#selectedInstances").attr("data-ids"));
                ids = JSON.parse($("#selectedInstances").attr("data-ids"));
                // The request is one call, so the real progress is not known: the bar
                // runs until it finishes. Without it the page just sat there.
                Swal.fire({
                    title: i18nMessages.resettingPasswords || "Resetting passwords",
                    html:
                        '<style>@keyframes rpSlide{0%{margin-left:-40%}100%{margin-left:100%}}</style>' +
                        '<div style="margin:14px 0 6px;color:#6b7280;font-size:14px">' +
                        ids.length + " " + (i18nMessages.resettingCount || "employee(s)") + "</div>" +
                        '<div style="height:8px;border-radius:6px;background:#eceef2;overflow:hidden">' +
                        '<div style="width:40%;height:100%;border-radius:6px;background:#e54f38;animation:rpSlide 1.1s ease-in-out infinite"></div></div>',
                    allowOutsideClick: false,
                    allowEscapeKey: false,
                    showConfirmButton: false,
                });
                $.ajax({
                    type: "POST",
                    url: "/employee/employee-bulk-reset-password-admin/",
                    data: {
                        csrfmiddlewaretoken: getCookie("csrftoken"),
                        ids: JSON.stringify(ids),
                    },
                    error: function () {
                        Swal.close();
                        Swal.fire({ text: i18nMessages.resetFailed || "Could not reset the passwords.", icon: "error" });
                    },
                    success: function (response, textStatus, jqXHR) {
                        Swal.close();
                        if (jqXHR.status === 200) {
                            $("#genericModalBody").html(response);
                            // Same class the declarative data-toggle="oh-modal-toggle"
                            // handler adds (ModalDialog.js openModal()) -- this is a
                            // JS-driven open (after a Swal confirm), not a raw click
                            // on an element carrying that attribute, so it has to be
                            // triggered directly here instead.
                            $("#genericModal").addClass("oh-modal--show");
                        }
                    },
                });
            }
        });
    }
});

$(document).on("click", "#sendInvitationEmployees", function (e) {
    e.preventDefault();
    ids = [];
    ids.push($("#selectedInstances").attr("data-ids"));
    ids = JSON.parse($("#selectedInstances").attr("data-ids"));
    if (ids.length === 0) {
        Swal.fire({
            text: i18nMessages.noRowsSelected,
            icon: "warning",
            confirmButtonText: i18nMessages.close,
        });
    } else {
        Swal.fire({
            text: i18nMessages.confirmBulkInvite,
            icon: "info",
            showCancelButton: true,
            confirmButtonColor: "#d33",
            cancelButtonColor: "#6c757d",
            confirmButtonText: i18nMessages.confirm,
            cancelButtonText: i18nMessages.cancel,
        }).then(function (result) {
            if (result.isConfirmed) {
                ids = [];
                ids.push($("#selectedInstances").attr("data-ids"));
                ids = JSON.parse($("#selectedInstances").attr("data-ids"));
                $.ajax({
                    type: "POST",
                    url: "/employee/employee-bulk-send-invitation/",
                    data: {
                        csrfmiddlewaretoken: getCookie("csrftoken"),
                        ids: JSON.stringify(ids),
                    },
                    success: function (response, textStatus, jqXHR) {
                        if (jqXHR.status === 200) {
                            reloadEmployeeListContainer();
                        }
                    },
                });
            }
        });
    }
});

$(document).on("click", "#employeeBulkUpdateId", function (e) {
    ids = [];
    ids.push($("#selectedInstances").attr("data-ids"));
    ids = JSON.parse($("#selectedInstances").attr("data-ids"));
    if (ids.length === 0) {
        $("#bulkUpdateModal").removeClass("oh-modal--show");
        Swal.fire({
            text: i18nMessages.noRowsSelected,
            icon: "warning",
            confirmButtonText: i18nMessages.close,
        });
    } else {
        $("#id_bulk_employee_ids").val(JSON.stringify(ids));
        $("#bulkUpdateModal").addClass("oh-modal--show");
    }
});


$(document).on("click", "#deleteEmployees", function (e) {
    e.preventDefault();
    ids = [];
    ids.push($("#selectedInstances").attr("data-ids"));
    ids = JSON.parse($("#selectedInstances").attr("data-ids"));
    if (ids.length === 0) {
        Swal.fire({
            text: i18nMessages.noRowsSelected,
            icon: "warning",
            confirmButtonText: i18nMessages.close,
        });
    } else {
        Swal.fire({
            text: i18nMessages.confirmBulkDelete,
            icon: "error",
            showCancelButton: true,
            confirmButtonColor: "#d33",
            cancelButtonColor: "#6c757d",
            confirmButtonText: i18nMessages.confirm,
            cancelButtonText: i18nMessages.cancel,
        }).then(function (result) {
            if (result.isConfirmed) {
                e.preventDefault();

                ids = [];
                ids.push($("#selectedInstances").attr("data-ids"));
                ids = JSON.parse($("#selectedInstances").attr("data-ids"));

                $.ajax({
                    type: "POST",
                    url: "/employee/employee-bulk-delete/",
                    data: {
                        csrfmiddlewaretoken: getCookie("csrftoken"),
                        ids: JSON.stringify(ids),
                    },
                    success: function (response, textStatus, jqXHR) {
                        if (jqXHR.status === 200) {
                            reloadEmployeeListContainer();
                        } else {
                            // console.log("Unexpected HTTP status:", jqXHR.status);
                        }
                    },
                });
            }
        });
    }
});
