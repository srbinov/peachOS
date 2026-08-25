import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import Shell from 'gi://Shell';
import Meta from 'gi://Meta';
import { matchIconForApp, lampTargetFromIcon } from './iconGeometry.js';

// these are hacks to make Dash2Dock Animated compatible with other Extensions
//
export const Integrations = class {
  enable() {
    this.hookCompiz();
    this.hookBms();
  }

  disable() {
    this.releaseCompiz();
    this.releaseBms();
  }

  hookCompiz(hook = true) {
    let compiz = Main.extensionManager.lookup(
      'compiz-alike-magic-lamp-effect@hermes83.github.com'
    );
    if (!compiz || !compiz.stateObj) {
      return;
    }
    let stateObj = compiz.stateObj;
    this._compiz = stateObj;
    if (hook) {
      if (!stateObj._getIcon) {
        stateObj._getIcon = stateObj.getIcon.bind(stateObj);
      }
      // Always override: the stock getIcon aims at the hidden GNOME dash
      // (screen center). The lamp-app-animation switch only used to
      // install this hook, so the effect never hit our icons.
      stateObj.getIcon = this.compiz_getIcon.bind(this);
    } else if (stateObj._getIcon) {
      stateObj.getIcon = stateObj._getIcon;
      stateObj._getIcon = null;
    }
  }

  releaseCompiz() {
    this.hookCompiz(false);
    this._compiz = null;
  }

  _createRect(x, y, width, height) {
    let props = {
      x: Math.round(x),
      y: Math.round(y),
      width: Math.max(1, Math.round(width)),
      height: Math.max(1, Math.round(height)),
    };
    if (Meta.Rectangle) {
      return new Meta.Rectangle(props);
    }
    try {
      return new imports.gi.Mtk.Rectangle(props);
    } catch (err) {
      return props;
    }
  }

  _iconScreenRect(icon) {
    let candidates = [icon._renderer, icon._icon, icon].filter((a) => a);
    for (let i = 0; i < candidates.length; i++) {
      let actor = candidates[i];
      if (!actor.get_transformed_position) {
        continue;
      }
      let pos = actor.get_transformed_position();
      if (
        !pos ||
        !Number.isFinite(pos[0]) ||
        !Number.isFinite(pos[1])
      ) {
        continue;
      }
      let width = actor.width || 0;
      let height = actor.height || 0;
      if (actor.get_transformed_size) {
        let sz = actor.get_transformed_size();
        if (sz && sz[0] > 0 && sz[1] > 0) {
          width = sz[0];
          height = sz[1];
        }
      }
      if (width <= 0 || height <= 0) {
        continue;
      }
      return { x: pos[0], y: pos[1], width, height };
    }
    return null;
  }

  _dockIconRecords() {
    let records = [];
    (this.extension.docks || []).forEach((dock) => {
      (dock._icons || []).forEach((icon) => {
        let app = icon._appwell?.app;
        if (!app) {
          return;
        }
        let rect = this._iconScreenRect(icon);
        if (!rect) {
          return;
        }
        let pids = [];
        try {
          pids = app.get_pids ? app.get_pids() : [];
        } catch (err) {
          pids = [];
        }
        records.push({
          dock,
          icon,
          appId: app.get_id(),
          pids,
          ...rect,
        });
      });
    });
    return records;
  }

  _iconForWindow(metaWindow) {
    if (!metaWindow) {
      return null;
    }
    let appId = null;
    try {
      let tracker = Shell.WindowTracker.get_default();
      let app = tracker.get_window_app(metaWindow);
      if (app) {
        appId = app.get_id();
      }
    } catch (err) {
      appId = null;
    }
    let pid = null;
    try {
      pid = metaWindow.get_pid();
    } catch (err) {
      pid = null;
    }
    return matchIconForApp(this._dockIconRecords(), { appId, pid });
  }

  updateWindowsIconGeometry() {
    (this.extension.docks || []).forEach((dock) => {
      (dock._icons || []).forEach((icon) => {
        let app = icon._appwell?.app;
        if (!app || !app.get_windows) {
          return;
        }
        let rect = this._iconScreenRect(icon);
        if (!rect) {
          return;
        }
        let box = this._createRect(rect.x, rect.y, rect.width, rect.height);
        app.get_windows().forEach((w) => {
          if (w.skip_taskbar) {
            return;
          }
          try {
            w.set_icon_geometry(box);
          } catch (err) {
            // GNOME 46 uses Meta.Rectangle, 48+ uses Mtk.Rectangle
          }
        });
      });
    });
  }

  // override compiz getIcon
  compiz_getIcon(actor) {
    let metaWindow = actor?.meta_window || actor?.get_meta_window?.();
    let matched = this._iconForWindow(metaWindow);
    if (matched) {
      return lampTargetFromIcon(
        matched,
        matched.dock._position,
        matched.dock._monitor
      );
    }

    let docks = this.extension.docks || [];
    let monitor =
      Main.layoutManager.monitors[metaWindow ? metaWindow.get_monitor() : 0];
    let dock =
      docks.find((d) => monitor && d._monitorIndex == monitor.index) ||
      docks[0];

    if (dock && dock._background && dock._monitor) {
      let pos = dock._background.get_transformed_position();
      let x = Number.isFinite(pos?.[0])
        ? pos[0] + dock._background.width / 2
        : dock._monitor.x + dock._monitor.width / 2;
      let y = Number.isFinite(pos?.[1]) ? pos[1] : dock._monitor.y;
      return lampTargetFromIcon(
        { x, y, width: 32, height: 32 },
        dock._position,
        dock._monitor
      );
    }

    if (monitor) {
      return lampTargetFromIcon(
        {
          x: monitor.x + monitor.width / 2,
          y: monitor.y + monitor.height,
          width: 32,
          height: 32,
        },
        'bottom',
        monitor
      );
    }

    return { x: 1, y: 1, width: 32, height: 32 };
  }

  hookBms(hook = true) {
    if (!hook) {
      this.extension.docks.forEach((dock) => {
        dock.animator._bms = null;
      });
    }

    let bms = Main.extensionManager.lookup('blur-my-shell@aunetx');
    this._bms = bms;
    if (bms && bms.stateObj && bms.metadata.version >= 70) {
      let obj = bms.stateObj;
      if (obj._dash_to_dock_blur) {
        if (!obj._dash_to_dock_blur.update_size_orig) {
          obj._dash_to_dock_blur.update_size_orig =
            obj._dash_to_dock_blur.update_size;
        }
        if (hook && this.extension.blur_background) {
          obj._dash_to_dock_blur.update_size = () => {};
        } else if (obj._dash_to_dock_blur.update_size_orig) {
          obj._dash_to_dock_blur.update_size =
            obj._dash_to_dock_blur.update_size_orig;
        }
      }
    }
  }

  releaseBms() {
    this.hookBms(false);
    this._bms = null;
  }

  bms_update_size(animator) {
    let dock = animator.dock;

    // blur my shell
    let bms = dock.get_children().find((child) => {
      let name = child.get_name();
      return name === 'bms-dash-backgroundgroup';
    });

    animator._bms = bms;

    if (!bms) {
      return;
    }

    bms.visible = dock.extension.blur_background;
    if (!bms.visible) {
      return;
    }

    // compatible blur-my-shell version 70
    // bms version 70 supports 46,47..up
    if (
      dock.extension.integrations._bms &&
      dock.extension.integrations._bms.metadata.version >= 70
    ) {
      let bg_offset_x = dock._background.x;
      let bg_offset_y = dock._background.y;
      let rw = dock.renderArea.width;
      let rh = dock.renderArea.height;

      let meta_background = bms.first_child.first_child;
      if (!meta_background) {
        // this should exists
        return;
      }

      // bottom layout
      switch (dock._position) {
        case 'left':
        case 'top':
          bms.x = 0;
          bms.y = 0;
          bms.first_child.x = 0;
          bms.first_child.y = 0;
          bms.first_child.set_clip(
            bg_offset_x,
            bg_offset_y,
            dock._background.width - (dock.extension.border_thickness && 0),
            dock._background.height - (dock.extension.border_thickness && 0)
          );
          break;
        case 'right':
          bms.x = 0;
          bms.y = 0;
          bms.first_child.x = -meta_background.width + rw;
          bms.first_child.y = 0;
          bms.first_child.set_clip(
            -bms.first_child.x + bg_offset_x,
            0 + bg_offset_y,
            dock._background.width - (dock.extension.border_thickness && 0),
            dock._background.height - (dock.extension.border_thickness && 0)
          );
          break;
        case 'bottom':
        default:
          bms.x = 0;
          bms.y = 0;
          bms.first_child.x = 0;
          bms.first_child.y = -meta_background.height + rh;
          bms.first_child.set_clip(
            0 + bg_offset_x,
            -bms.first_child.y + bg_offset_y,
            dock._background.width - (dock.extension.border_thickness && 0),
            dock._background.height - (dock.extension.border_thickness && 0)
          );
          break;
      }

      let opacity = (dock.extension.background_color[3] ?? 0.5) * 54 + 200;
      meta_background.opacity = opacity;

      animator._blur_effects = bms.first_child.get_effects();
      if (animator._blur_effects) {
        animator._blur_effects.forEach((e) => {
          if (e.constructor.name == 'CornerEffect') {
            e.radius = dock.extension.computed_border_radius;
          }
        });
      }

      return;
    }

    // bms version incompatible
    bms.visible = false;
  }
};
