import customtkinter as ctk
try:
    app = ctk.CTk()
    combo = ctk.CTkComboBox(app, values=["1", "2"])
    print("Has _on_dropdown_menu_button_click:", hasattr(combo, "_on_dropdown_menu_button_click"))
    print("Has _open_dropdown_menu:", hasattr(combo, "_open_dropdown_menu"))
    
    # List all methods starting with _on_ or _open
    print("Methods starting with _on_ or _open:")
    for attr in dir(combo):
        if attr.startswith("_on_") or attr.startswith("_open"):
            print(attr)
except Exception as e:
    print(e)
