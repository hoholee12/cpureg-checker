import sys
import subprocess
import argparse
from cpureg.cpureg_parser import CpuRegParser

class CpuRegApp:
    def __init__(self):
        self.parser = CpuRegParser()

    def check_gcc(self):
        try:
            subprocess.run(["gcc", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        except subprocess.CalledProcessError:
            print("GCC is not installed or not found in PATH.")
            sys.exit(1)
        except FileNotFoundError:
            print("GCC is not installed or not found in PATH.")
            sys.exit(1)

    def main(self):
        self.check_gcc()

        arg_parser = argparse.ArgumentParser()
        group = arg_parser.add_mutually_exclusive_group()
        group.add_argument("-g", "--generate", type=str, choices=self.parser.supported_platforms,
                           help="generate preprocessed functions & callstacks")
        group.add_argument("-p", "--process", action="store_true", help="process and spit out rights & wrongs on your code")

        arg_parser.add_argument("-I", "--include", action="append", metavar="INCLUDE_PATH", type=str, help="include path for the generate option")

        group.add_argument("-c", "--caller", type=str, help="print caller stack of function (test)")
        group.add_argument("-C", "--callee", type=str, help="print caller stack before reaching function (test)")
        arg_parser.add_argument("-s", "--sourceview", action="store_true", help="launch the source viewer GUI")

        args = arg_parser.parse_args()
        target_platform = args.generate
        incpaths = args.include or []

        if target_platform:
            if len(incpaths) == 0:
                arg_parser.error("generate requires at least one include path")

            srcpaths = self.parser.parse_per_target_platform(target_platform, incpaths)
            self.parser.parse_workspace_cleanup()
            self.parser.parse_functions(srcpaths, incpaths)

        elif args.process:
            pass

        elif args.caller:
            self.parser.get_caller_flow("", args.caller)
            pass
        elif args.callee:
            self.parser.get_callee_flow(args.callee)
            pass

        elif args.sourceview:
            from cpureg.source_viewer import SourceViewer
            from PySide6.QtWidgets import QApplication

            app = QApplication()            
            app.setStyleSheet(SourceViewer.dark_stylesheet)
            viewer = SourceViewer()
            viewer.show()
            sys.exit(app.exec())
        else:
            arg_parser.print_help()
            sys.exit(1)

if __name__ == "__main__":
    CpuRegApp().main()