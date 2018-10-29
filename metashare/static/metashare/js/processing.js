/**
 * Created by mdel on 26-Mar-18.
 */

$(document).ready(function () {
    $('#processing-form').on('submit', function (event) {
        event.preventDefault();
        var formData = new FormData($('form')[0]);
        $('#msg').removeClass();
        $('#msg').text('');
        $('#progress-wrappper').toggle();

        if (formData.get("repo-resource-id") != null){
            $('#progress-wrappper').hide();
            $('#processing-form').ajaxSubmit({
                success: function (data) {
                    $('#processing-form')[0].reset();
                    $('#msg').addClass(data.msg.status);
                    $('#msg').text(data.msg.message);
                }
            });
            return true
        }

        var fileSize = $("#zipfile")[0].files[0].size;

        if(fileSize > 31457280){
            $('#msg').addClass("alert alert-warning");
            $('#msg').text("The file you are trying to upload " +
                "is larger than the maximum upload file size (30 MB)!");
            resetProgress($('#progress-wrappper'));
            return false;
        }

        $.ajax({
            xhr: function () {
                var xhr = new window.XMLHttpRequest();
                xhr.upload.addEventListener('progress', function (e) {
                    if (e.lengthComputable) {
                        var percent = Math.round((e.loaded / e.total) * 100);
                        $('#progressBar').attr('aria-valuenow', percent)
                            .css('width', percent + '%')
                            .text(percent+'%');
                    }
                });

                return xhr;
            },
            type: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            success: function (data) {
                resetProgress($('#progress-wrappper'));
                $('#processing-form')[0].reset();
                $('#msg').addClass(data.msg.status);
                $('#msg').text(data.msg.message);
            }
        });
    });
});


function resetProgress(prog) {
    $('#progressBar').attr('aria-valuenow', 0)
                            .css('width', 0 + '%')
                            .text(0+'%');
    prog.toggle()
}







