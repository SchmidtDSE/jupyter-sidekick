import {
  ILayoutRestorer,
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';
import { ICommandPalette } from '@jupyterlab/apputils';
import { ILauncher } from '@jupyterlab/launcher';
import { LabIcon } from '@jupyterlab/ui-components';

import acpSvgStr from '../style/icons/acp.svg';
import { AcpChatPanel } from './widget';

const OPEN = 'jupyter-acp:open';
const NEW = 'jupyter-acp:new-chat';

export const acpIcon = new LabIcon({
  name: 'jupyter-acp:icon',
  svgstr: acpSvgStr
});

const plugin: JupyterFrontEndPlugin<void> = {
  id: 'jupyter-acp:plugin',
  description: 'Zed-style ACP chat for JupyterLab.',
  autoStart: true,
  optional: [ICommandPalette, ILauncher, ILayoutRestorer],
  activate: (
    app: JupyterFrontEnd,
    palette: ICommandPalette | null,
    launcher: ILauncher | null,
    restorer: ILayoutRestorer | null
  ) => {
    // One persistent chat docked in the left sidebar (icon-only). Drag the
    // tab to the right via right-click → "Switch Sidebar Side".
    let sidebar: AcpChatPanel | null = null;
    const ensureSidebar = (): AcpChatPanel => {
      if (sidebar === null || sidebar.isDisposed) {
        sidebar = new AcpChatPanel();
        sidebar.id = 'jupyter-acp-sidebar';
        sidebar.title.icon = acpIcon;
        sidebar.title.caption = 'ACP Chat'; // tooltip only — no text label
        app.shell.add(sidebar, 'left', { rank: 900 });
        if (restorer) {
          restorer.add(sidebar, 'jupyter-acp-sidebar');
        }
      }
      return sidebar;
    };

    // Additional chats open as main-area tabs: multiple at once, freely
    // draggable/splittable, with the file browser still docked.
    let counter = 0;
    const newMainChat = (): void => {
      counter += 1;
      const panel = new AcpChatPanel();
      panel.id = `jupyter-acp-chat-${Date.now()}-${counter}`;
      panel.title.icon = acpIcon;
      panel.title.label = `ACP Chat ${counter}`;
      panel.title.closable = true;
      app.shell.add(panel, 'main');
      app.shell.activateById(panel.id);
    };

    ensureSidebar();

    app.commands.addCommand(OPEN, {
      label: 'ACP Chat (sidebar)',
      caption: 'Reveal the docked ACP chat panel',
      icon: acpIcon,
      execute: () => app.shell.activateById(ensureSidebar().id)
    });
    app.commands.addCommand(NEW, {
      label: 'New ACP Chat',
      caption: 'Open a new ACP chat in the main area',
      icon: acpIcon,
      execute: () => newMainChat()
    });

    if (palette) {
      palette.addItem({ command: NEW, category: 'AI' });
      palette.addItem({ command: OPEN, category: 'AI' });
    }
    if (launcher) {
      launcher.add({ command: NEW, category: 'Other', rank: 1 });
    }
  }
};

export default plugin;
