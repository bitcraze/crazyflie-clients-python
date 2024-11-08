from PyQt6 import QtWidgets

def test_main_ui_window(qtbot, main_window,local):

    qtbot.addWidget(main_window)
    main_window.show()
    assert main_window.isVisible()
    if local:
        qtbot.wait(1000)
    main_window.close()
    assert not main_window.isVisible()



def test_tab_visibility(qtbot,main_window,local):
    def test_tab(name):
        tab_name = name
        tab_action_item = next((a for a in main_window.tabs_menu_item.actions() if a.text() == tab_name), None)
        assert tab_action_item is not None, f"Tab action for '{tab_name}' not found"

        assert not tab_action_item.isChecked()
        tab_action_item.triggered.emit(True)
        assert tab_action_item.isChecked()
    # Create an instance of the main UI window
    qtbot.addWidget(main_window)

    main_window.show()
    tab_list = ["Console","Parameters","Loco Positioning","Lighthouse Positioning","Crtp sniffer","Log TOC", "LED","Log Blocks","Plotter", "Tuning", "Log Client"]
    for tab_name in tab_list:
        test_tab(tab_name)
    if local:
        qtbot.wait(1000)

def test_toolbox_visibility(qtbot,main_window,local):
    def test_toolbox(name):
        tab_name = name
        tab_action_item = next((a for a in main_window.toolboxes_menu_item.actions() if a.text() == tab_name), None)
        assert tab_action_item is not None, f"Tab action for '{tab_name}' not found"

        assert not tab_action_item.isChecked()
        tab_action_item.triggered.emit(True)
        assert tab_action_item.isChecked()
    # Create an instance of the main UI window
    qtbot.addWidget(main_window)

    main_window.show()
    tab_list = ["Console","Parameters","Loco Positioning","Lighthouse Positioning","Crtp sniffer","Log TOC", "LED","Log Blocks","Plotter", "Tuning", "Log Client"]
    for tab_name in tab_list:
        test_toolbox(tab_name)
    if local:
        qtbot.wait(1000)
