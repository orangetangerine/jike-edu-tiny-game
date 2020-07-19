# -*- coding: utf-8 -*-
# Author: orange
# Date: 2020-07-19
#

import threading, time, os, sys

import hashlib
from asciimatics.widgets import Frame, ListBox, Layout, Divider, VerticalDivider, \
    Text, Button, TextBox, Widget, Label, PopupMenu, PopUpDialog, RadioButtons
from asciimatics.scene import Scene
from asciimatics.screen import Screen
from asciimatics.exceptions import ResizeScreenError, NextScene, StopApplication

from protocol import game_pb2
from protocol import game_pb2_grpc
import grpc

channel = None

_seq = 0  # global seq id, multi thread lock?

#  gender const
Gender_Female = 1
Gender_Male = 2

user_list = []

# global sha256 hash
def hasher(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def seq() -> int:
    global _seq
    _seq += 1
    return _seq


class Err(object):
    def __init__(self, metadata: dict = None):
        if metadata is None:
            metadata = {}
        self.code = metadata.get("resp_code", 0)
        self.msg = metadata.get("resp_msg", "")

    @staticmethod
    def new(msg: str):
        _err = Err()
        _err.code = -2
        _err.msg = msg
        return _err

    def __str__(self):
        return f"{self.msg}, {self.code}"


logF = open('log.log', 'w', encoding='utf-8')


def log(*m):
    print(m, file=logF)


def prepare(url='localhost:50000'):
    global channel
    channel = grpc.insecure_channel(url)
    channel = channel


class Game:
    @staticmethod
    def Register(name, nickname, pwd, gender):
        if name is None or len(name.strip()) == 0:
            err = Err.new("账号不能为空")
            log(err.__str__())
            return err
        if nickname is None or len(nickname.strip()) == 0:
            err = Err.new("昵称不能为空")
            log(err.__str__())
            return err
        if pwd is None or len(pwd.strip()) == 0:
            err = Err.new("密码不能为空")
            log(err.__str__())
            return err

        stub = game_pb2_grpc.GameStub(channel)
        resp, call = stub.Register.with_call(game_pb2.RegisterReq(
            account=name,
            nickname=nickname,
            password=hasher(pwd),
            gender=game_pb2.MALE if gender == Gender_Male else game_pb2.FEMALE
        ))
        resp_metadata = {i[0]: i[1] for i in call.initial_metadata()}
        if resp_metadata.get("resp_code", "0") != "0":
            err = Err(resp_metadata)
            log('register failed,', err)
            return err

        return None

    @staticmethod
    def Login(name, pwd):
        if pwd is None or len(pwd.strip()) == 0:
            err = Err.new("密码不能为空")
            log(err.__str__())
            return err

        stub = game_pb2_grpc.GameStub(channel)
        resp, call = stub.Login.with_call(game_pb2.LoginReq(
            account=name,
            password=hasher(pwd),
        ))
        resp_metadata = {i[0]: i[1] for i in call.initial_metadata()}
        if resp_metadata.get("resp_code", "0") != "0":
            err = Err(resp_metadata)
            log('login failed,', err)
            return None, err

        global my, user_metadata
        my = UserModal(resp.user_info.user_id, resp.user_info.nickname)
        my.token = resp.token
        my.refresh_token = resp.refresh_token
        user_metadata = (("token", my.token), ("user-id", "%d" % my.uid),)
        # ff.add_done_callback(fn)
        # print(resp.token)

        _user_list, err = Game.GetOnlineUsers(my.uid)
        if err is not None:
            log("GetOnlineUsers", err)
            return None, err

        global user_list
        user_list.clear()
        user_list.extend(_user_list)
        return my, None

    @staticmethod
    def GetOnlineUsers(my_id):
        stub = game_pb2_grpc.GameStub(channel)
        resp, call = stub.GetOnlineUsers.with_call(game_pb2.GetOnlineUsersReq(), metadata=user_metadata)
        resp_metadata = {i[0]: i[1] for i in call.initial_metadata()}
        if resp_metadata.get("resp_code", "0") != "0":
            err = Err(resp_metadata)
            log('login failed,', err)
            return None, err

        ul = []
        for u in resp.users:
            log(u)
            if u.user_id == my_id:
                continue
            ul.append((u.nickname, u.user_id))
        return ul, None

    @staticmethod
    def Battle(target_uid):
        stub = game_pb2_grpc.BattleStub(channel)
        log(user_metadata)
        resp, call = stub.BattleLite.with_call(game_pb2.BattleLiteReq(
            target_uid=target_uid,
        ), metadata=user_metadata)
        resp_metadata = {i[0]: i[1] for i in call.initial_metadata()}
        log(resp_metadata)
        if resp_metadata.get("resp_code", "0") != "0":
            err = Err(resp_metadata)
            log('battle failed,', err)
            return None, err
        return resp, None


class UserModal(object):
    def __init__(self, uid, nickname):
        self.uid = uid
        self.nickname = nickname


# noinspection PyTypeChecker
my = UserModal(0, "")  # just init
user_metadata = (('user-id', '%d' % 0),)  # just init


class MainView(Frame):
    def __init__(self, screen):
        super(MainView, self).__init__(screen,
                                       10,
                                       100,
                                       on_load=self._onload,
                                       hover_focus=True,
                                       can_scroll=False,
                                       title="Main")
        layout = Layout([1, 1, 1], fill_frame=False)
        # layout = Layout([1,1,1], fill_frame=False)
        self.add_layout(layout)
        layout.add_widget(Button("login", self._login), 0)
        layout.add_widget(Button("register", self._register), 1)
        layout.add_widget(Button("quit", self._quit), 2)
        self.fix()

    def _onload(self):
        pass

    def _login(self):
        raise NextScene("Login")
        pass

    def _register(self):
        raise NextScene("Register")
        pass

    def _quit(self):
        raise StopApplication("bye")
        pass


class RegisterView(Frame):
    def __init__(self, screen):
        super(RegisterView, self).__init__(screen,
                                           10, 50,
                                           on_load=self._onload,
                                           hover_focus=True,
                                           can_scroll=False,
                                           title="Register Page")
        layout = Layout([1])
        self.add_layout(layout)
        self._text_name = Text("账号:", "name")
        self._text_nickname = Text("昵称:", "nickname")
        self._text_pwd = Text("密码:", "pwd", hide_char="*")
        self._radio_gender = RadioButtons([("Girl", Gender_Female),
                                           ("Boy", Gender_Male)],
                                          label="性别",
                                          name="gender")
        self._radio_gender.value = Gender_Female
        layout.add_widget(self._text_name)
        layout.add_widget(self._text_nickname)
        layout.add_widget(self._text_pwd)
        layout.add_widget(self._radio_gender)
        layout.add_widget(Button("注册", self._register))
        layout.add_widget(Button("取消", self._cancel))
        self.fix()

    def _onload(self):
        pass

    def _register(self):
        username = self._text_name.value
        nickname = self._text_nickname.value
        pwd = self._text_pwd.value
        gender = self._radio_gender.value
        err = Game.Register(username, nickname, pwd, gender)
        if err is not None:
            self._scene.add_effect(
                PopUpDialog(self._screen, err.__str__(), ["OK"]))
            return

        raise NextScene('Main')

    def _cancel(self):
        raise NextScene("Main")


class LoginView(Frame):
    def __init__(self, screen):
        super(LoginView, self).__init__(screen,
                                        10,
                                        50,
                                        on_load=self._onload,
                                        hover_focus=True,
                                        can_scroll=False,
                                        title="Login Page")
        layout = Layout([1])
        self.add_layout(layout)
        self._text_name = Text("账号:", "name")
        self._text_pwd = Text("密码:", "pwd", hide_char="*")
        layout.add_widget(self._text_name)
        layout.add_widget(self._text_pwd)
        layout.add_widget(Button("login", self._login))
        layout.add_widget(Button("cancel", self._cancel))
        self.fix()

    def _onload(self):
        pass

    def _login(self):
        username = self._text_name.value
        pwd = self._text_pwd.value
        _my, err = Game.Login(username, pwd)
        if err is not None:
            self._scene.add_effect(
                PopUpDialog(self._screen, err.__str__(), ["OK"]))
            return

        raise NextScene("Game")

    def _cancel(self):
        raise NextScene("Main")


class GameView(Frame):
    def __init__(self, screen):
        super(GameView, self).__init__(screen,
                                       40,
                                       100,
                                       on_load=self._onload,
                                       hover_focus=True,
                                       can_scroll=False,
                                       title="Game Page")
        self.messages = []

        main_layout = Layout([7, 1, 2])
        self.add_layout(main_layout)
        self.my_label = Label("")  # my nick name
        main_layout.add_widget(self.my_label, 0)
        main_layout.add_widget(Label("messages:"), 0)
        msg_list = ListBox(30, self.messages, add_scroll_bar=True)
        # msg_list.disabled = True
        main_layout.add_widget(msg_list, 0)
        main_layout.add_widget(VerticalDivider(), 1)
        main_layout.add_widget(Label("online users:"), 2)
        main_layout.add_widget(Button("refresh", self._refresh_users), 2)
        global user_list
        self.list_users = ListBox(30, user_list,
                                  # [("老王的甜糕", 1), ("阿故的植物", 2), ("怡宝的鸭子", 3), ("凉妹子的iPad Mini", 4),
                                  #  ("当归的长发", 5),
                                  #  ],
                                  on_select=self._on_user_select)
        main_layout.add_widget(self.list_users, 2)

        div_layout = Layout([1])
        self.add_layout(div_layout)
        div_layout.add_widget(Divider())

        ctl_layout = Layout([1, 1, 1, 1])
        self.add_layout(ctl_layout)
        # TODO
        ctl_layout.add_widget(Button("战斗", self._fight), 0)
        ctl_layout.add_widget(Button("背包", self._package), 1)
        ctl_layout.add_widget(Button("信息", self._info), 2)
        ctl_layout.add_widget(Button("退出", self._quit), 3)
        # ctl_layout.add_widget(Button("test", None))
        self.fix()

    def _onload(self):
        self.my_label._text = "欢迎你, " + my.nickname
        # pass

    def clear_msg(self):
        self.messages.clear()

    def _fight(self):
        # TODO
        self._scene.add_effect(
            PopUpDialog(self._screen, "还没做完", ["OK"]))
        pass

    def _info(self):
        # TODO
        fake_info = f"""{my.nickname}
Lv. 1
HP: 100
攻击力: 5
防御力: 5
命中: 1
回避: 1
        """
        self._scene.add_effect(
            PopUpDialog(self._screen, fake_info, ["OK"]))
        pass

    def _package(self):
        # TODO
        self._scene.add_effect(
            PopUpDialog(self._screen, "背包还没做完", ["OK"]))
        pass

    def _quit(self):
        def _yes_no(selected):
            if selected == 0:
                raise StopApplication("bye")

        self._scene.add_effect(
            PopUpDialog(self._screen, "确定咩", ["OK", "NO"], on_close=_yes_no))

    def _refresh_users(self):
        # TODO
        self._scene.add_effect(
            PopUpDialog(self._screen, "还没做完", ["OK"]))

    def _on_user_select(self):
        self.clear_msg()
        widget = self.list_users
        widget.disabled = True
        self._screen.force_update()
        log(self.list_users.value)

        resp, err = Game.Battle(self.list_users.value)  # test
        if err is not None:
            self._scene.add_effect(
                PopUpDialog(self._screen, err.__str__(), ["OK"]))
            return

        _msgs = self.messages

        def on_update(m):
            _msgs.append(m)
            self.list_users.value = len(_msgs) - 1
            self._screen.force_update()

        def on_done():
            widget.disabled = False
            self._screen.force_update()

        class myThread(threading.Thread):
            def __init__(self, threadID, msgs, update_fn, done_fn):
                threading.Thread.__init__(self)
                self.threadID = threadID
                self.msgs = msgs
                self._update_fn = update_fn
                self._done_fn = done_fn

            def run(self):
                global seq
                for m in self.msgs:
                    self._update_fn((m.content, seq()))  # must be list or tuple
                    time.sleep(0.1)
                    # self.sc.force_update()
                self._update_fn((">战斗结束<", seq()))
                self._done_fn()
                # end run

        t1 = myThread(1, resp.msg, on_update, on_done)
        t1.start()


def main(screen, scene):
    scenes = [
        Scene([MainView(screen)], -1, name="Main"),
        Scene([RegisterView(screen)], -1, name="Register"),
        Scene([LoginView(screen)], -1, name="Login"),
        Scene([GameView(screen)], -1, name="Game"),
    ]

    screen.play(scenes, stop_on_resize=True, start_scene=scene, allow_int=True)


if __name__ == '__main__':
    url = 'localhost:50000'
    if len(sys.argv) > 1:
        url = sys.argv[1]

    prepare(url)

    last_scene = None
    while True:
        try:
            Screen.wrapper(main, catch_interrupt=False, arguments=[last_scene])
            sys.exit(0)
        except ResizeScreenError as e:
            last_scene = e.scene
