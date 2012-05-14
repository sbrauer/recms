function setup_name_generator() {
    if(! $("input:text[name=name]").length) { return; }
    if(! $("input:text[name=title]").length) { return; }
    $("input:text[name=name]").after(' <input type="button" value="generate from title" id="generate_name_button"/>');
    $("#generate_name_button").click(function() {
        var SEP = "-";
        var title = $("input:text[name=title]").val();
        if(! title) { return; }
        title = title.toLowerCase();
        var name = "";
        var i, ch;
        for(i=0; i < title.length; i++) {
            ch = title[i];
            if((ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9')) {
                name += ch;
            } else if (ch=="'" || ch=='"') {
                continue;
            } else {
                if(name) {
                    var lastCh = name.charAt(name.length - 1);
                    if(lastCh == SEP) { continue; }
                }
                name += SEP;
            }
        }
        // Strip any leading SEP.
        if(name) {
            var ch = name.charAt(0);
            if(ch == SEP) { name = name.substring(1); }
        }
        // Strip any trailing SEP.
        if(name) {
            var ch = name.charAt(name.length - 1);
            if(ch == SEP) { name = name.substring(0, name.length-1); }
        }
        $("input:text[name=name]").val(name);
    });
}

// Change class of table rows when checkboxes are checked/unchecked.
function setup_checkbox_change_callback(form_selector) {
    var callback = function() {
        if($(this).attr("checked")) {
            $(this).parents("tr").addClass("checked");
        } else {
            $(this).parents("tr").removeClass("checked");
        }
    };
    $(form_selector+" input:checkbox").change(callback);
    $(form_selector+" input:checkbox").each(callback);
}

// Used on the folder_contents page.
function setup_contents_checkboxes() {
    $("#invert_selection_container").append('<input type="checkbox" name="invert_selection" id="invert_selection_checkbox" title="invert selected checkboxes" /> ');
    $("#invert_selection_checkbox").click(function() {
        $("#contents_form input:checkbox").each(function() {
            if($(this).attr("checked")) {
                $(this).attr("checked", false);
                $(this).parents("tr").removeClass("checked");
            } else {
                $(this).attr("checked", true);
                $(this).parents("tr").addClass("checked");
            }
        });
    });
    setup_checkbox_change_callback("#contents_form");
}

// Used on the local_roles page.
function setup_form_radios() {
    function update_radio_classes() {
        $("#role_form input:radio").each(function() {
            if($(this).attr("checked")) {
                $(this).parents("td").addClass("checked");
            } else {
                $(this).parents("td").removeClass("checked");
            }
        });
    }
    $("#role_form input:radio").change(function() {
        update_radio_classes();
    });
    // Call once when form loads.
    update_radio_classes();
}

function setup_help() {
    $(".help_link").colorbox({width:"700px", maxHeight:"90%"});
}
