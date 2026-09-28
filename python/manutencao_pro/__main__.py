from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    if len(args) > 1 and args[1] == "--demo-stream":
        from manutencao_pro.demo import stream_main

        return stream_main(args[2:])
    from manutencao_pro.i18n import install

    install()
    from manutencao_pro.application import ManutencaoApplication

    app = ManutencaoApplication()
    return app.run(args)


if __name__ == "__main__":
    sys.exit(main())
