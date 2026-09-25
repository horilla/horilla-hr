function clearQueryString() {
  var url = window.location.href;
  var newUrl = url.split('?')[0];
  history.replaceState(null, '', newUrl);
}

var savedFilters = localStorage.getItem("savedFilters");
if (savedFilters != null) {
  var filterDetails = JSON.parse(savedFilters);
  if (window.location.pathname == filterDetails.currentPath) {
    let filterForm = $(filterDetails.formSelector);
    for (var fieldName in filterDetails.filterData) {
      if (filterDetails.filterData.hasOwnProperty(fieldName)) {
        var value = filterDetails.filterData[fieldName];
        // Set the value of the corresponding form field
        let field = filterForm.find('[name="' + fieldName + '"]');
        if (
          field.attr("data-exclude-saved-filter") != "true" &&
          (field.val() == "" || field.val() == "unknown")
        ) {
          field.val(value);
          field.first().change();
        }
      }
    }
    setTimeout(() => {
      filterForm.find(".filterButton").click();
      clearQueryString();
      setTimeout(() => {
        $("#main-section-data:first").show();
        $("#tripple-loader-contaner:first").remove();
      }, 350);
    }, 250);
  } else {
    var savedFilters = localStorage.removeItem("savedFilters");
    clearQueryString();
    $("#main-section-data:first").show();
    $("#tripple-loader-contaner:first").remove();
  }
} else {
  clearQueryString();
  $("#main-section-data:first").show();
  $("#tripple-loader-contaner:first").remove();
}
$(document).ready(function () {
  $(".filterButton").click(function (e) {
    var filterForm = $(this).parents().closest("form");
    var currentPath = window.location.pathname;
    var formDataArray = filterForm.serializeArray();
    var filterData = {};
    formDataArray.forEach(function (item) {
      if (filterData.hasOwnProperty(item.name)) {
        if (!Array.isArray(filterData[item.name])) {
          filterData[item.name] = [filterData[item.name]];
        }
        filterData[item.name].push(item.value);
      } else {
        filterData[item.name] = item.value;
      }
    });
    var filterDetails = {
      currentPath: currentPath,
      formSelector: "form" + `[hx-get="${filterForm.attr("hx-get")}"]`,
      filterData: filterData,
    };
    localStorage.setItem("savedFilters", JSON.stringify(filterDetails));
  });
});
