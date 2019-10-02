from __future__ import annotations

from collections import namedtuple
from datetime import datetime
from textwrap import TextWrapper
from typing import List, Dict, Any, Union, Optional, Type

from PIL import Image
from pandas import DataFrame, Series
from urllib3 import HTTPResponse
from colorama import Fore, Style, Back

from .exceptions import *
from .html_handlers import get_response
from .banners import Banner, description
from .img_to_ascii import convert
from .drivers import fetch_drivers, fetch_driver
from .result_tables import fetch_results
from .news import fetch_top_stories

Command = namedtuple("Command", ['cmd', 'label'])
Option = namedtuple("Option", ['opt', 'label'])
Message = namedtuple("Message", ['msg', 'type'])


class Context:
    history: List[Any] = []
    messages: List[Message] = []
    block_render: bool = True

    def __init__(self) -> None:
        self.name: str = "context"
        self.state: Dict[str, Any] = {}
        self.custom_commands: List[Command] = []
        self.command: str = ""
        self.menu_options: List[Option] = []
        self.next_ctx_args: Dict[str, Any] = {}
        self.next_ctx = None
        self.show_banner = False

    def __str__(self):
        return self.name

    def render(self) -> None:
        if self.show_banner:
            print(self.banner)
        self.show_options()
        self.event()
        print()
        self.show_messages()
        self.show_commands()
        if self.block_render:
            cmd: str = self._get_commands()
            if cmd.lower() == "q":
                raise ExitException
            elif cmd.lower() == "m":
                self.next_ctx = MainContext
                self.next_ctx_args = {}
                return
            elif cmd.lower() == "b":
                try:
                    self.__class__.history.pop()
                    self.next_ctx = self.__class__.history[-1]
                    self.next_ctx_args = {}
                except IndexError:
                    self.next_ctx = MainContext
                    self.next_ctx_args = {}
                return

            else:
                self.command = cmd.lower()

        self.action_handler()

    def action_handler(self) -> None:
        pass

    def event(self) -> None:
        pass

    def add_to_history(self) -> None:
        self.__class__.history.append(self)

    def show_options(self) -> None:
        template = "[{}]  {}"
        for option in self.menu_options:
            self._pprint(template.format(option.opt, option.label), margin=2)
        print()

    def show_messages(self) -> None:
        messages: List[Message] = self.__class__.messages

        while messages:
            message: Message = messages.pop()
            if message.type == "error":
                self._pprint(f"{Fore.RED}{message.msg}{Style.RESET_ALL}", margin=10)
            elif message.type == "success":
                self._pprint(f"{Fore.LIGHTGREEN_EX}{message.msg}{Style.RESET_ALL}", margin=10)
            elif message.type == "debug":
                self._pprint(f"{Fore.LIGHTCYAN_EX}{message.msg}{Style.RESET_ALL}", margin=10)

    def show_commands(self, template: str = "[{}] {}") -> None:
        commands: List[Command] = []
        commands += self.custom_commands

        if len(self.__class__.history) > 1:
            commands.append(Command(cmd="b", label="Back"))
        commands += [
            Command(cmd="m", label="Menu"),
            Command(cmd="q", label="Quit")
        ]
        self._pprint("\nCommands", 30)
        for i, command in enumerate(commands):
            if command.cmd in ['b', 'm']:
                print()
            elif i % 2 == 0:
                print()
            print(str(" " * 2) + template.format(command.cmd, command.label), end=" ")
        print()

    def _get_commands(self) -> str:
        cmd: str = ""
        try:
            cmd = str(input(">> ")).strip()
        except EOFError:
            self.__class__.messages.append(Message(msg="Invalid Command", type="error"))
        return cmd

    @property
    def banner(self):
        banner = Banner()
        return str(banner) + "\n" + description

    @staticmethod
    def _pprint(text, margin=10, end="\n"):
        for line in text.split('\n'):
            print(Style.RESET_ALL + " " * margin + line, end=end)


class MainContext(Context):
    def __init__(self) -> None:
        super().__init__()
        self.name = "Main Menu"
        self.menu_options = [
            Option(opt=1, label="Driver Standing"),
            Option(opt=2, label="Constructor Standing"),
            Option(opt=3, label="Races Results"),
            Option(opt=4, label="Fastest Laps"),
            Option(opt=5, label="Drivers"),
            Option(opt=6, label="Latest News"),
        ]
        self.custom_commands = [Command(cmd="NUMBER", label="Select Option"), ]
        self.state = {"tables": ["drivers", "team", "races", "fastest-laps"]}
        self.show_banner = True

    def action_handler(self) -> None:
        try:
            cmd: int = int(self.command)
        except ValueError:
            self.__class__.messages.append(Message(msg="Invalid Command", type="Error"))
            self.next_ctx = self
            return
        if cmd in [1, 2, 3, 4]:
            self.next_ctx = ResultTableContext
            self.next_ctx_args = {"table_for": self.state["tables"][cmd - 1]}
        elif cmd == 5:
            self.next_ctx = DriversContext
            self.next_ctx_args = {}
        elif cmd == 6:
            self.next_ctx = NewsListContext
            self.next_ctx_args = {}


class ResultTableContext(Context):
    def __init__(self, table_for: str,
                 table: Optional[DataFrame] = None,
                 year: Optional[int] = None,
                 title: str = "") -> None:
        super().__init__()
        self.name = table_for.replace("-", " ").title()
        self.state = {
            'for': table_for,
            'year': year if year else datetime.now().year,
            'table': table,
            'title': title
        }
        if self.state['table'] is None:
            self._fetch_table()

        self.custom_commands = [Command(cmd="y:YEAR", label="Change Season"), ]

    def event(self) -> None:
        table: str = self.state['table'].to_string(index=False)
        self._pprint(self.title, 35)
        self._pprint(table, 10)
        print()

    def action_handler(self) -> None:
        cmd: str = self.command
        if cmd.lower().startswith("y:"):
            year: int = int(cmd.split(':')[1])
            self.next_ctx = ResultTableContext
            self.next_ctx_args = {
                "table_for": self.state["for"], "year": year, "table": None}
            self.__class__.messages.append(Message(msg=f"Season changed to {year}", type="success"))
            return
        self.next_ctx = self

    def _fetch_table(self) -> None:
        try:
            table: DataFrame = fetch_results(self.state['for'], self.state['year'])
        except ValueError:
            table = fetch_results(self.state['for'], self.state['year'])
            self.state['year'] = datetime.now().year
            self.__class__.messages.append(Message(msg=f"Invalid Season. [1950-{self.state['year']}]", type="error"))
        self.state['table'] = table

    @property
    def title(self) -> str:
        if self.state["title"]:
            return self.state["title"]

        titles: Dict[str, str] = {
            "drivers": "Drivers Championship",
            "team": "Constructor Championship",
            "races": "Race Results",
            "fastest-laps": "DHL Fastest Lap Award"
        }
        year: int = self.state["year"]
        return f"{year} {titles[self.state['for']]}\n"


class DriversContext(Context):
    def __init__(self, drivers: Optional[DataFrame] = None) -> None:
        super().__init__()
        self.state = {'drivers': drivers}
        self.custom_commands = [Command(cmd="INDEX", label="Select Driver"), ]

    def event(self) -> None:
        drivers: Optional[DataFrame] = self.state["drivers"]
        if drivers is None:
            drivers = fetch_drivers()
            drivers.index += 1
            self.state["drivers"] = drivers
        # TODO: Context.printDataFrametable()
        self._pprint("Drivers\n", 30)
        self._pprint(drivers[["NAME", "NUMBER", "TEAM"]].to_string(), 10)
        print("\n")

    def action_handler(self) -> None:
        cmd: str = self.command
        if cmd and cmd.isdecimal():
            try:
                index: int = int(cmd) - 1
                drivers: DataFrame = self.state["drivers"]
                driver: Series = drivers.iloc[index, :]
                self.next_ctx = DriverContext
                self.next_ctx_args = {'driver': driver, 'driver_index': index, 'drivers': drivers}
            except IndexError:
                self.__class__.messages.append(Message(msg="Invalid Driver Index", type="error"))
                self.next_ctx = self


class DriverContext(Context):
    drivers_history: Dict[int, Context] = {}

    def __init__(self, driver: Union[Series, Dict[str, str]], driver_index: int, drivers: DataFrame) -> None:
        super().__init__()
        self.state = {
            'driver': driver,
            'portrait': None,
            'info': None,
            'index': driver_index,
            'drivers': drivers,
            'max_drivers': len(drivers) - 1
        }
        self.custom_commands = [
            Command(cmd='bio', label="Read Bio"),
            Command(cmd='d', label="Next Driver"),
            Command(cmd='a', label="Previous Driver")
        ]
        self.__class__.drivers_history[driver_index] = self

        header = Back.LIGHTWHITE_EX
        driver_names = list(drivers["NAME"])
        for name in driver_names:
            if name == driver["NAME"]:
                header += Fore.RED
                header += Back.WHITE
                header += name.split(' ')[-1]
                header += Back.LIGHTWHITE_EX
                header += Fore.RESET
            else:
                header += Fore.LIGHTBLACK_EX
                header += Style.DIM
                header += name.split(' ')[-1]
                header += Fore.RESET
            header += "  "
        else:
            header += Back.RESET
        self.header = header

    def event(self) -> None:
        self._pprint(self.header + "\n", margin=2)

        portrait: Optional[str] = self.state['portrait']
        if portrait is None:
            portrait = self.make_portrait(self.state['driver']['IMG'])
            self.state['portrait'] = portrait
        self._pprint(portrait, 7)

        driver: Union[Dict[str, str]] = dict(self.state['driver'])

        driver_info: Optional[Dict[str, str]] = self.state['info']
        if driver_info is None:
            driver_info = fetch_driver(driver['URL'])
            self.state['info'] = driver_info
        driver.update(driver_info)

        m: int = 30
        for label, value in driver.items():
            if label not in ['BIO', 'URL', 'IMG']:
                row = label.title() + ":" + str(" " * (m - len(label))) + value
                self._pprint(row, 2)
        print()

    def action_handler(self) -> None:
        cmd: str = self.command

        if cmd.lower() == 'bio':
            self.next_ctx = TextContext
            self.next_ctx_args = {'text': self.state['info']['BIO']}

        elif cmd.lower() in ['d', 'a']:
            drivers = self.state['drivers']
            driver_idx = self.state['index']
            next_idx = driver_idx + 1 if cmd.lower() == 'd' else driver_idx - 1

            if next_idx > self.state['max_drivers']:
                next_idx = 0
            elif next_idx < 0:
                next_idx = self.state['max_drivers']

            next_driver: Union[Type[DriverContext], Series] = \
                self.__class__.drivers_history.get(next_idx, drivers.iloc[next_idx, :])

            if isinstance(next_driver, DriverContext):
                self.next_ctx = next_driver
                self.next_ctx_args = {}
            else:
                self.next_ctx = DriverContext
                self.next_ctx_args = {'driver': next_driver, 'driver_index': next_idx, 'drivers': drivers}

        else:
            self.next_ctx = self

    @staticmethod
    def make_portrait(img_url: str) -> str:
        im_bytes: HTTPResponse = get_response(img_url, b=True)
        im: Image = Image.open(im_bytes)
        return convert(im, colored=True)


class NewsListContext(Context):
    def __init__(self) -> None:
        super().__init__()
        self.state = {

        }

    def event(self) -> None:
        # TODO
        stories: DataFrame = fetch_top_stories()
        story: Series
        for i, story in stories.iterrows():
            print(self.article_headline(story, i))

    def action_handler(self) -> None:
        self.next_ctx = self

    @staticmethod
    def article_headline(story: Series, index: Optional[int] = None, line: int = 200) -> str:
        headline: str = f"[{index}] {story['headline']} - tags: [{', '.join(story.tags)}]"
        sep: str = str("-" * (line + 10))
        headline = sep + "\n" + headline + "\n" + sep

        return headline

    @staticmethod
    def _longest_headline(headlines: Series) -> int:
        print("Longest", len(headlines.max()))
        return len(headlines.max())


class TextContext(Context):
    def __init__(self, text: str, width: int = 80) -> None:
        super().__init__()
        self.text: str = text
        self.width: int = width

    def event(self) -> None:
        wrapper: TextWrapper = TextWrapper(width=self.width)
        word_list: List[str] = wrapper.wrap(text=self.text)
        for element in word_list:
            self._pprint(element, 3)
        print()

    def action_handler(self) -> None:
        self.next_ctx = self
