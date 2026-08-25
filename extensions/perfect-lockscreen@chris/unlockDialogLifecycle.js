export function nextUnlockDialogAction({ sessionMode, dialog, appliedDialog, shieldActive }) {
    if (sessionMode === 'gdm')
        return 'none';

    if (shieldActive === false && appliedDialog)
        return 'teardown';

    if (shieldActive === false)
        return 'wait';

    if (dialog && appliedDialog && dialog !== appliedDialog)
        return 'reapply';

    if (dialog && !appliedDialog)
        return 'apply';

    if (!dialog && appliedDialog)
        return 'teardown';

    return dialog && appliedDialog === dialog ? 'none' : 'wait';
}
