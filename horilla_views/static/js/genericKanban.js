var groupOrder = []

function getBoardConfig($anchor) {
	var $helper = $anchor.closest(".hlv-container").find("#helperContainer");
	return {
		modelName: $helper.attr("data-model"),
		kanbanUrl: $helper.attr("data-kanban-url"),
		preMoveCheckUrl: $helper.attr("data-pre-move-check-url"),
		csrfToken: $helper.find('input[name="csrfmiddlewaretoken"]').val(),
	};
}

function getBoardStageOrder($anchor) {
	return $anchor
		.closest(".hlv-container")
		.find(".pipeline_item")
		.map(function () {
			return {
				id: parseInt($(this).attr("data-group-id"), 10),
				stage: $(this).attr("data-group-instance"),
			};
		})
		.get();
}

function adjustGroupCount(groupId, delta) {
	var $badge = $("#groupCount" + groupId);
	var current = parseInt($badge.text(), 10) || 0;
	$badge.text(current + delta);
}

function isNextStage(currentStageId, targetStageId, parsedStageOrder) {
	var currentStageIndex = parsedStageOrder.findIndex(
		(stage) => stage.id == currentStageId
	);
	var targetStageIndex = parsedStageOrder.findIndex(
		(stage) => stage.id == targetStageId
	);
	return (
		targetStageIndex === currentStageIndex + 1 ||
		currentStageIndex === targetStageIndex
	);
}

function groupSequenceGet(groupHead) {
	var sequence = [];
	var groupContainers = groupHead.closest('.groupContainer').find(".pipeline_item")
	var config = getBoardConfig(groupHead);

	$.each(groupContainers, function (index, element) {
		sequence.push($(element).attr("data-group-id"));
	});

	$.ajax({
		type: "POST",
		url: config.kanbanUrl,
		headers: { "HX-Request": "true" },
		data: {
			csrfmiddlewaretoken: config.csrfToken,
			kanban_action: "reorder-groups",
			sequence: JSON.stringify(sequence),
			tab_id: groupHead.attr("data-tab-id"),
		},
		success: function () {
			$("#reloadMessagesButton").click();
		},
		error: function () {
			$("#reloadMessagesButton").click();
		},
	});
}

// Objects whose move request is still in flight, so a second drop of the
// same card cannot send a duplicate request.
var pendingKanbanMoves = {};

// Reload the recruitment vacancy indicator (present on the recruitment
// pipeline only) once a move has changed who is selected.
function refreshVacancyBadge() {
	var badge = document.querySelector(".vp[data-refresh-url]");
	if (badge && window.htmx) {
		window.htmx.ajax("GET", badge.getAttribute("data-refresh-url"), {
			target: badge,
			swap: "outerHTML",
		});
	}
}

function handleValidDrop(groupId, objectId, row) {
	if (!groupId || !objectId) {
		return;
	}
	if (pendingKanbanMoves[objectId]) {
		revertItemPosition({ item: row });
		return;
	}
	if (groupId != window.candidateCurrentStage) {
		var originalGroupId = window.candidateCurrentStage;
		var container = row.closest(".pipeline_item");
		var array = container.find(".task-card");
		if (!array.length) {
			array = container.find("[data-instance-id]");
		}

		var values = [];
		for (let i = 0; i < array.length; i++) {
			values.push($(array[i]).attr("data-instance-id"));
		}
		if (!values.length) {
			return;
		}

		var config = getBoardConfig(row);
		pendingKanbanMoves[objectId] = true;

		function sendMove(confirmed) {
			var data = {
				csrfmiddlewaretoken: config.csrfToken,
				kanban_action: "move-item",
				groupId: groupId,
				order: JSON.stringify(values),
			};
			if (confirmed) {
				data.confirm = 1;
			}
			$.ajax({
				type: "POST",
				url: config.kanbanUrl,
				headers: { "HX-Request": "true" },
				traditional: true,
				data: data,
				success: function () {
					row.find(`[name="group_id"]`).val(groupId);
					adjustGroupCount(originalGroupId, -1);
					adjustGroupCount(groupId, 1);

					$("#reloadMessagesButton").click();
					refreshVacancyBadge();
					delete pendingKanbanMoves[objectId];
				},
				error: function (xhr) {
					var body = xhr.responseJSON || {};
					if (body.needs_confirmation) {
						// Nothing was saved. Ask first; Cancel puts the card back.
						Swal.fire({
							title: typeof gettext !== "undefined" ? gettext("Vacancy Filled") : "Vacancy Filled",
							text: body.message,
							icon: "warning",
							showCancelButton: true,
							confirmButtonColor: "#008000",
							cancelButtonColor: "#6c757d",
							confirmButtonText: typeof i18nMessages !== "undefined" ? i18nMessages.ok : "Ok",
							cancelButtonText: typeof i18nMessages !== "undefined" ? i18nMessages.cancel : "Cancel",
						}).then(function (result) {
							if (result.isConfirmed) {
								sendMove(true);
							} else {
								revertItemPosition({ item: row });
								delete pendingKanbanMoves[objectId];
							}
						});
						return;
					}
					// Nothing was saved: put the card back.
					revertItemPosition({ item: row });
					$("#reloadMessagesButton").click();
					delete pendingKanbanMoves[objectId];
				},
			});
		}
		sendMove(false);
	}
}

function handleSortableUpdate(event, ui, container) {
	var array = container.find(".task-card");
	if (!array.length) {
		array = container.find("[data-instance-id]");
	}
	var groupId = $(ui.item).closest(".pipeline_item").attr("data-group-id") || $(ui.item).data("group");

	var values = [];
	for (let i = 0; i < array.length; i++) {
		values.push($(array[i]).attr("data-instance-id"));
	};
	if (!groupId || !values.length) {
		return;
	}

	var config = getBoardConfig(container);

	$.ajax({
		type: "POST",
		url: config.kanbanUrl,
		headers: { "HX-Request": "true" },
		traditional: true,
		data: {
			csrfmiddlewaretoken: config.csrfToken,
			kanban_action: "reorder-items",
			groupId: groupId,
			order: JSON.stringify(values),
		},
		success: function (response) {
			$(".reload-badge").click();
			$("#reloadMessagesButton").click();

			if (response.info) {
				console.warn(response.info)
			}
		},
		error: function () {
			$("#reloadMessagesButton").click();
		}
	});
}

function initializeSortable() {
	$(".groupContainer")
		.sortable({
			handle: ".oh-kanban__section-head",
			cursor: "grabbing",
			connectWith: ".pipeline_item",
			placeholder: "group-placeholder",

			start: function (event, ui) {
				const $stage = $(ui.item).find(".kanban-head");
				if ($stage.length === 0) return;

				window["tabId"] = $stage.attr("data-tab-id");
				window["groupSequence"] = $(this).attr("data-group-sequence");
				window["oldSequences"] = [];
				window["groups"] = [];
				window["elements"] = [];

				$(".kanban-head").each(function (i, obj) {
					if (tabId == $(obj).attr("data-tab-id")) {
						window["groups"].push($(obj).attr("data-group-id"));
						window["oldSequences"].push($(obj).attr("data-group-sequence"));
					}
				});
			},

			stop: function (event, ui) {
				const $stage = $(ui.item).find(".kanban-head");
				if ($stage.length === 0) return;

				var newSequences = [];

				setTimeout(() => {
					groupSequenceGet($stage);
				}, 0);

				$(".kanban-head").each(function (i, obj) {
					if (
						tabId == $(obj).attr("data-tab-id") ||
						$(obj).attr("data-tab-id") == undefined
					) {
						newSequences.push($(obj).attr("data-group-sequence"));
						if ($(obj).attr("data-tab-id") != undefined) {
							window["elements"].push(obj);
						}
					}
				});

				if (newSequences.includes(undefined)) {
					newSequences = newSequences.filter((e) => e !== groupSequence);
					newSequences = newSequences.map((elem) =>
						elem === undefined ? stageSequence : elem
					);
				}

				oldSequences = JSON.stringify(oldSequences);
				groups = JSON.stringify(groups);

				elements.forEach(function (element) {
					for (let index = 0; index < newSequences.length; index++) {
						const sequence = newSequences[index];
						if (sequence == $(element).attr("data-group-sequence")) {
							$(element).attr("data-group-sequence", `${index + 1}`);
							return;
						}
					}
				});

				// Reset
				window["groupSequence"] = null;
				window["tabId"] = null;
				window["oldSequences"] = [];
				window["elements"] = [];
				window["groups"] = [];
			},
		})
		.disableSelection();
}

function initializeKanbanSortable(sectionSelector, stageSelector) {

	$(sectionSelector).sortable({
		connectWith: sectionSelector,
		items: "> :not(.htmx-indicator)",
		ghostClass: "blue-background-class",
		cursor: "grabbing",
		placeholder: "sortable-placeholder",
		forcePlaceholderSize: true,
		appendTo: "body",
		zIndex: 9999,
		helper: function (event, ui) {
			var helper = ui.clone();
			var width = ui.outerWidth() + "px";
			helper.css({
				width: width,
				"max-width": width,
				"min-width": width,
				"box-sizing": "border-box"
			});
			return helper;
		},

		start: function (event, ui) {
			var row = $(ui.item);
			var nodeId = row.closest(stageSelector).attr("data-group-id");
			var currentStage = parseInt(nodeId);

			if (isNaN(currentStage)) {
				currentStage = nodeId
			}

			window.candidateCurrentStage = currentStage;
			ui.item.data("origin-parent", ui.item.parent());
			ui.item.data("origin-index", ui.item.index());
		},

		stop: function (event, ui) {
			var self = this;
			var row = $(ui.item);
			var candidateId = row.data("instanceId");
			var nodeId = row.closest(stageSelector).attr("data-group-id");
			var targetStageId = parseInt(nodeId);

			if (isNaN(targetStageId)) {
				targetStageId = nodeId
			}

			var originalStageId = window.candidateCurrentStage;
			var stageChanged = targetStageId != originalStageId;
			var config = getBoardConfig(row);

			function applyMove() {
				if (stageChanged) {
					handleValidDrop(targetStageId, candidateId, row);
				} else {
					handleSortableUpdate(event, ui, $(self));
				}
			}

			function proceedWithMove() {
				var parsedStageOrder = getBoardStageOrder(row);
				var preStage = parsedStageOrder.find(stage => stage.id == originalStageId);
				var currentStage = parsedStageOrder.find(stage => stage.id == targetStageId);

				if (!isNextStage(originalStageId, targetStageId, parsedStageOrder)) {
					if (sessionStorage.getItem(`showKanban${config.modelName}Confirmation`) !== "false") {
						Swal.fire({
							title: typeof gettext !== "undefined" ? gettext("Confirm Stage Change") : "Confirm Stage Change",
							html: `
                                <p class="mb-2">${typeof interpolate !== "undefined" && typeof gettext !== "undefined"
									? interpolate(
										gettext("The candidate is being moved from %(from)s to the %(to)s stage. Do you want to proceed?"),
										{ from: preStage.stage, to: currentStage.stage },
										true
									)
									: `The candidate is being moved from ${preStage.stage} to the ${currentStage.stage} stage. Do you want to proceed?`
								}</p>
                                <label><input type="checkbox" id="doNotShowAgain"> ${typeof gettext !== "undefined" ? gettext("Don't show this again in this session") : "Don't show this again in this session"}</label>
                            `,
							icon: "warning",
							showCancelButton: true,
							cancelButtonColor: "#6c757d",
							confirmButtonColor: "#008000",
							confirmButtonText: i18nMessages.confirm,
							cancelButtonText: typeof i18nMessages !== "undefined" ? i18nMessages.cancel : "Cancel",
							preConfirm: () => {
								const doNotShowAgain = Swal.getPopup().querySelector("#doNotShowAgain").checked;
								if (doNotShowAgain) {
									sessionStorage.setItem(`showKanban${config.modelName}Confirmation`, "false");
								}
							},
						}).then((result) => {
							if (result.isConfirmed) {
								applyMove();
							} else {
								revertItemPosition(ui);
							}
						});
						return;
					}
				}

				applyMove();
			}

			if (config.preMoveCheckUrl && targetStageId != originalStageId) {
				$.ajax({
					type: "GET",
					url: config.preMoveCheckUrl,
					data: {
						objectId: candidateId,
						groupId: targetStageId,
					},
					success: function (response) {
						if (response.blocked) {
							Swal.fire({
								icon: "error",
								title: typeof gettext !== "undefined" ? gettext("Cannot Change Stage") : "Cannot Change Stage",
								text: response.message || (typeof gettext !== "undefined" ? gettext("This move is not allowed.") : "This move is not allowed."),
								confirmButtonText: typeof i18nMessages !== "undefined" ? i18nMessages.ok : "Ok",
							});
							revertItemPosition(ui);
						} else {
							proceedWithMove();
						}
					},
					error: function () {
						proceedWithMove();
					},
				});
				return;
			}

			proceedWithMove();
		}
	});
}

function revertItemPosition(ui) {
	const originParent = ui.item.data("origin-parent");
	const originIndex = ui.item.data("origin-index");

	if (originParent && originIndex !== undefined) {
		const currentItem = ui.item.detach();
		const children = originParent.children();

		if (originIndex >= children.length) {
			originParent.append(currentItem);
		} else {
			currentItem.insertBefore(children.eq(originIndex));
		}

		originParent.sortable("refresh");
	}
}

$(document).ready(function () {
	initializeKanbanSortable(".oh-kanban__section-body", ".pipeline_item");
});
