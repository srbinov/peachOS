import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { nextUnlockDialogAction } from '../unlockDialogLifecycle.js';

describe('nextUnlockDialogAction', () => {
    const dialogA = { id: 'a' };
    const dialogB = { id: 'b' };

    it('waits when the user session has no unlock dialog yet', () => {
        assert.equal(
            nextUnlockDialogAction({ sessionMode: 'user', dialog: null, appliedDialog: null }),
            'wait'
        );
    });

    it('applies Cupertino chrome when a new unlock dialog appears', () => {
        assert.equal(
            nextUnlockDialogAction({ sessionMode: 'unlock-dialog', dialog: dialogA, appliedDialog: null }),
            'apply'
        );
    });

    it('does nothing when the current dialog is already set up', () => {
        assert.equal(
            nextUnlockDialogAction({ sessionMode: 'unlock-dialog', dialog: dialogA, appliedDialog: dialogA }),
            'none'
        );
    });

    it('reapplies when the shell replaces the unlock dialog', () => {
        assert.equal(
            nextUnlockDialogAction({ sessionMode: 'user', dialog: dialogB, appliedDialog: dialogA }),
            'reapply'
        );
    });

    it('tears down when unlocking destroys the dialog', () => {
        assert.equal(
            nextUnlockDialogAction({ sessionMode: 'user', dialog: null, appliedDialog: dialogA }),
            'teardown'
        );
    });

    it('tears down when the screen shield deactivates even if the dialog still exists', () => {
        assert.equal(
            nextUnlockDialogAction({
                sessionMode: 'user',
                dialog: dialogA,
                appliedDialog: dialogA,
                shieldActive: false,
            }),
            'teardown'
        );
    });

    it('does not apply while unlocked even if a leftover dialog object exists', () => {
        assert.equal(
            nextUnlockDialogAction({
                sessionMode: 'user',
                dialog: dialogA,
                appliedDialog: null,
                shieldActive: false,
            }),
            'wait'
        );
    });

    it('never patches the in-session UnlockDialog while in GDM', () => {
        assert.equal(
            nextUnlockDialogAction({ sessionMode: 'gdm', dialog: dialogA, appliedDialog: null }),
            'none'
        );
    });
});
