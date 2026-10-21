odoo.define('purchase_requisition_custom.binary_dropzone', function (require) {
'use strict';

const basicFields = require('web.basic_fields');
const core = require('web.core');
const fieldRegistry = require('web.field_registry');
const utils = require('web.utils');

const _t = core._t;
const qweb = core.qweb;

/**
 * Binary file widget with a drop area: files can be dragged onto the area,
 * pasted with Ctrl+V anywhere in the form, or picked with the native file
 * dialog by clicking the area. Once a file is obtained, it goes through the
 * native FieldBinaryFile upload flow (filename sync, value set, re-render).
 */
const FieldBinaryDropzone = basicFields.FieldBinaryFile.extend({
    events: _.extend({}, basicFields.FieldBinaryFile.prototype.events, {
        'dragenter .o_prc_dropzone': '_onDragOver',
        'dragover .o_prc_dropzone': '_onDragOver',
        'dragleave .o_prc_dropzone': '_onDragLeave',
        'drop .o_prc_dropzone': '_onDrop',
        'click .o_prc_dropzone': '_onDropzoneClick',
        'keydown .o_prc_dropzone': '_onDropzoneKeydown',
    }),

    /**
     * Supports a 'max_file_size_mb' option to lower the server-wide upload
     * limit. It overrides max_upload_size, which the native file picker
     * (on_file_change) also checks, so every upload path honors it.
     *
     * @override
     */
    init: function () {
        this._super.apply(this, arguments);
        const maxFileSizeMb = this.nodeOptions && this.nodeOptions.max_file_size_mb;
        if (maxFileSizeMb) {
            this.max_upload_size = Math.min(this.max_upload_size, maxFileSizeMb * 1024 * 1024);
        }
        this.maxUploadSizeLabel = utils.human_size(this.max_upload_size);
        this._onDocumentPaste = this._onDocumentPaste.bind(this);
        this._onDocumentDragOrDrop = this._onDocumentDragOrDrop.bind(this);
    },
    /**
     * @override
     */
    start: function () {
        document.addEventListener('paste', this._onDocumentPaste);
        document.addEventListener('dragover', this._onDocumentDragOrDrop);
        document.addEventListener('drop', this._onDocumentDragOrDrop);
        return this._super.apply(this, arguments);
    },
    /**
     * @override
     */
    destroy: function () {
        document.removeEventListener('paste', this._onDocumentPaste);
        document.removeEventListener('dragover', this._onDocumentDragOrDrop);
        document.removeEventListener('drop', this._onDocumentDragOrDrop);
        this._super.apply(this, arguments);
    },

    //--------------------------------------------------------------------------
    // Private
    //--------------------------------------------------------------------------

    /**
     * Document-level handlers only act while this widget is editable, visible
     * and inside the topmost dialog (so a dialog opened on top of the line
     * form, e.g. a many2one search, keeps the default behavior).
     *
     * @private
     * @returns {boolean}
     */
    _isActive: function () {
        if (this.mode !== 'edit' || !this.el || this.el.offsetParent === null) {
            return false;
        }
        const modal = this.el.closest('.modal');
        if (modal) {
            const modals = document.querySelectorAll('.modal');
            return modals[modals.length - 1] === modal;
        }
        return true;
    },
    /**
     * @private
     * @param {string} name
     * @returns {boolean}
     */
    _isAcceptedFile: function (name) {
        const accepted = (this.accepted_file_extensions || '*').split(',')
            .map(ext => ext.trim().toLowerCase())
            .filter(Boolean);
        // Only extension lists are checked here; mimetype filters (e.g. 'image/*')
        // are left to the server-side constraint.
        if (!accepted.length || accepted.some(ext => !ext.startsWith('.'))) {
            return true;
        }
        const lowerName = name.toLowerCase();
        return accepted.some(ext => lowerName.endsWith(ext));
    },
    /**
     * Browsers name clipboard screenshots 'image.png'; give them a unique,
     * meaningful name instead.
     *
     * @private
     * @param {File} file
     * @returns {string}
     */
    _getFileName: function (file) {
        if (file.name && file.name !== 'image.png') {
            return file.name;
        }
        const pad = num => String(num).padStart(2, '0');
        const now = new Date();
        const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_` +
            `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
        const extension = (file.type && file.type.split('/')[1]) || 'png';
        return `pasted_image_${stamp}.${extension}`;
    },
    /**
     * Single entry point for dropped and pasted files: validates the file and
     * hands it to the native upload flow.
     *
     * @private
     * @param {File} file
     */
    _uploadFile: function (file) {
        if (!file) {
            return;
        }
        const name = this._getFileName(file);
        if (!this._isAcceptedFile(name)) {
            this.displayNotification({
                title: _t("File upload"),
                message: _.str.sprintf(_t("File type not allowed. Allowed: %s"), this.accepted_file_extensions),
                type: 'danger',
            });
            return;
        }
        if (file.size > this.max_upload_size) {
            this.displayNotification({
                title: _t("File upload"),
                message: _.str.sprintf(_t("The selected file exceed the maximum file size of %s."), utils.human_size(this.max_upload_size)),
                type: 'danger',
            });
            return;
        }
        utils.getDataURLFromFile(file).then(data => {
            this.on_file_uploaded(file.size, name, file.type, data.split(',')[1]);
        });
    },
    /**
     * Adds the drop area, shown only while there is no file. When a file is
     * set, the native filename / edit / clear controls are used instead.
     *
     * @override
     * @private
     */
    _renderEdit: function () {
        this._super.apply(this, arguments);
        let $dropzone = this.$('.o_prc_dropzone');
        if (!$dropzone.length) {
            $dropzone = $(qweb.render('purchase_requisition_custom.BinaryDropzoneArea', {widget: this}));
            this.$el.append($dropzone);
        }
        $dropzone.toggleClass('o_hidden', !!this.value);
        if (!this.value) {
            // the drop area replaces the native "Upload your file" button
            this.$('.o_select_file_button').addClass('o_hidden');
        }
    },

    //--------------------------------------------------------------------------
    // Handlers
    //--------------------------------------------------------------------------

    /**
     * @private
     * @param {DragEvent} ev
     */
    _onDocumentDragOrDrop: function (ev) {
        // Prevent the browser from opening a file dropped outside the drop
        // area, which would leave the page and lose unsaved changes.
        if (!this._isActive() || !ev.dataTransfer || !_.contains(ev.dataTransfer.types, 'Files')) {
            return;
        }
        if (!ev.target.closest || !ev.target.closest('.o_prc_dropzone')) {
            ev.preventDefault();
            ev.dataTransfer.dropEffect = 'none';
        }
    },
    /**
     * @private
     * @param {ClipboardEvent} ev
     */
    _onDocumentPaste: function (ev) {
        const files = ev.clipboardData && ev.clipboardData.files;
        if (!this._isActive() || !files || !files.length) {
            // plain text keeps pasting normally in the focused input
            return;
        }
        ev.preventDefault();
        this._uploadFile(files[0]);
    },
    /**
     * @private
     * @param {jQuery.Event} ev
     */
    _onDragOver: function (ev) {
        ev.preventDefault();
        ev.originalEvent.dataTransfer.dropEffect = 'copy';
        this.$('.o_prc_dropzone').addClass('o_prc_dropzone_active');
    },
    /**
     * @private
     * @param {jQuery.Event} ev
     */
    _onDragLeave: function (ev) {
        // ignore leaving towards a child element of the drop area
        if (ev.currentTarget.contains(ev.originalEvent.relatedTarget)) {
            return;
        }
        this.$('.o_prc_dropzone').removeClass('o_prc_dropzone_active');
    },
    /**
     * @private
     * @param {jQuery.Event} ev
     */
    _onDrop: function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.$('.o_prc_dropzone').removeClass('o_prc_dropzone_active');
        const files = ev.originalEvent.dataTransfer.files;
        if (files && files.length) {
            this._uploadFile(files[0]);
        }
    },
    /**
     * @private
     */
    _onDropzoneClick: function () {
        this.$('.o_input_file').click();
    },
    /**
     * @private
     * @param {jQuery.Event} ev
     */
    _onDropzoneKeydown: function (ev) {
        if (ev.key === 'Enter' || ev.key === ' ') {
            ev.preventDefault();
            this._onDropzoneClick();
        }
    },
});

fieldRegistry.add('binary_dropzone', FieldBinaryDropzone);

return FieldBinaryDropzone;
});
