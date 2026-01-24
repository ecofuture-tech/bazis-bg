
$(function() {

    $('#changelist-form [name="action"]').change(function (){
        var file_load_block = $('#changelist-form [name="file_load"]').parent();
        file_load_block.css('display', 'none');
        if(window.actions_task_load) {
            if ($.inArray($(this).val(), actions_task_load) !== -1) {
                file_load_block.removeAttr('style');
            }
        }
    });

    $('#changelist-form [name="action"]').change();

});


