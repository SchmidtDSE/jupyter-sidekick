import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';
import { ICommandPalette, MainAreaWidget } from '@jupyterlab/apputils';
import { ILauncher } from '@jupyterlab/launcher';

import { AcpChatPanel } from './widget';

const COMMAND = 'jupyter-acp:new-chat';

const plugin: JupyterFrontEndPlugin<void> = {
  id: 'jupyter-acp:plugin',
  description: 'Zed-style ACP chat for JupyterLab.',
  autoStart: true,
  optional: [ICommandPalette, ILauncher],
  activate: (
    app: JupyterFrontEnd,
    palette: ICommandPalette | null,
    launcher: ILauncher | null
  ) => {
    app.commands.addCommand(COMMAND, {
      label: 'New ACP Chat',
      caption: 'Start a chat bound to an ACP agent',
      execute: () => {
        const content = new AcpChatPanel();
        const widget = new MainAreaWidget({ content });
        widget.id = `jupyter-acp-${Date.now()}`;
        widget.title.label = 'ACP Chat';
        widget.title.closable = true;
        app.shell.add(widget, 'main');
        app.shell.activateById(widget.id);
      }
    });

    if (palette) {
      palette.addItem({ command: COMMAND, category: 'AI' });
    }
    if (launcher) {
      launcher.add({ command: COMMAND, category: 'Other', rank: 1 });
    }
  }
};

export default plugin;
