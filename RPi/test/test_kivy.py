def test_kivy():
    try:
        import kivy
        print(f"import kivy succeeded - ver {kivy.version}")

        from kivy.app import App
        from kivy.uix.label import Label
        print("import kivy default module succeeded")

        # 간단한 앱 테스트
        class TestApp(App):
            def build(self):
                return Label(text='kivy test succeeded')

        print("make kivy app class succeeded")
        return True

    except Exception as e:
        print(f"kivy error: {e}")
        return False

if __name__ == "__main__":
    test_kivy()