"""
Module with all the individual handlers, which execute git commands and return the results to the frontend.
"""

import fnmatch
import functools
import json
import os
from pathlib import Path
from typing import Tuple, Union

import tornado
from jupyter_server.base.handlers import APIHandler, path_regex
from jupyter_server.services.contents.manager import ContentsManager
from jupyter_server.utils import ensure_async, url2path, url_path_join
from packaging.version import parse
from jupyter_server.auth.decorator import authorized

try:
    import hybridcontents
except ImportError:
    hybridcontents = None

from ._version import __version__
from .git import DEFAULT_REMOTE_NAME, Git, RebaseAction
from .log import get_logger

from .ssh import SSH
from .auth_providers import get_provider
from .token_storage import get_token_storage

# Git configuration options exposed through the REST API
ALLOWED_OPTIONS = ["user.name", "user.email"]
# REST API namespace
NAMESPACE = "/git"
# SSH Auth Resource to be authorized
SSH_AUTH_RESOURCE = "ssh"


class SSHHandler(APIHandler):
    """
    Top-level parent class for SSH actions
    """

    auth_resource = SSH_AUTH_RESOURCE

    @property
    def ssh(self) -> SSH:
        return SSH()


class GitHandler(APIHandler):
    """
    Top-level parent class.
    """

    @property
    def git(self) -> Git:
        return self.settings["git"]

    async def prepare(self):
        """Check if the path should be skipped"""
        await ensure_async(super().prepare())
        path = self.path_kwargs.get("path")
        if path is not None:
            excluded_paths = self.git.excluded_paths
            for excluded_path in excluded_paths:
                if fnmatch.fnmatchcase(path, excluded_path):
                    raise tornado.web.HTTPError(404)

    @functools.lru_cache()
    def url2localpath(
        self, path: str, with_contents_manager: bool = False
    ) -> Union[str, Tuple[str, ContentsManager]]:
        """Get the local path from a JupyterLab server path.

        Optionally it can also return the contents manager for that path.
        """
        cm = self.contents_manager

        # Handle local manager of hybridcontents.HybridContentsManager
        if hybridcontents is not None and isinstance(
            cm, hybridcontents.HybridContentsManager
        ):
            _, cm, path = hybridcontents.hybridmanager._resolve_path(path, cm.managers)

        local_path = os.path.join(os.path.expanduser(cm.root_dir), url2path(path))
        return (local_path, cm) if with_contents_manager else local_path


class GitCloneHandler(GitHandler):
    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        Handler for the `git clone`

        Input format:
            {
              'repo_url': 'https://github.com/path/to/myrepo',
              OPTIONAL 'auth': {
                'username': '<username>',
                'password': '<password>',
                'cache_credentials': true/false
              },
              # Whether to version the clone (True) or copy (False) it.
              OPTIONAL 'versioning': True,
              # Whether to clone the submodules or not.
              OPTIONAL 'submodules': False
            }
        """
        data = self.get_json_body()
        response = await self.git.clone(
            self.url2localpath(path),
            data["clone_url"],
            data.get("auth", None),
            data.get("versioning", True),
            data.get("submodules", False),
        )

        if response["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(response))


class GitAllHistoryHandler(GitHandler):
    """
    Parent handler for all four history/status git commands:
    1. git show_top_level
    2. git branch
    3. git log
    4. git status
    Called on refresh of extension's widget
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler, calls individual handlers for
        'git show_top_level', 'git branch', 'git log', and 'git status'
        """
        body = self.get_json_body()
        history_count = body["history_count"]
        local_path = self.url2localpath(path)

        show_top_level = await self.git.show_top_level(local_path)
        if show_top_level.get("path") is None:
            self.set_status(500)
            self.finish(json.dumps(show_top_level))
        else:
            branch = await self.git.branch(local_path)
            log = await self.git.log(local_path, history_count)
            status = await self.git.status(local_path)

            result = {
                "code": show_top_level["code"],
                "data": {
                    "show_top_level": show_top_level,
                    "branch": branch,
                    "log": log,
                    "status": status,
                },
            }
            self.finish(json.dumps(result))


class GitShowTopLevelHandler(GitHandler):
    """
    Handler for 'git rev-parse --show-toplevel'.
    Displays the git root directory inside a repository.
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler, displays the git root directory inside a repository.
        """
        result = await self.git.show_top_level(self.url2localpath(path))

        if result["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(result))


class GitShowPrefixHandler(GitHandler):
    """
    Handler for 'git rev-parse --show-prefix'.
    Displays the prefix path of a directory in a repository,
    with respect to the root directory.
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler, displays the prefix path of a directory in a repository,
        with respect to the root directory.
        """
        local_path, cm = self.url2localpath(path, with_contents_manager=True)
        result = await self.git.show_prefix(local_path, cm)

        if result["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(result))


class GitFetchHandler(GitHandler):
    """
    Handler for 'git fetch'
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler, fetch from remotes.
        """
        data = self.get_json_body()
        result = await self.git.fetch(
            self.url2localpath(path),
            data.get("auth", None),
        )

        if result["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(result))


class GitStatusHandler(GitHandler):
    """
    Handler for 'git status --porcelain', fetches the git status.
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler, fetches the git status.
        """
        result = await self.git.status(self.url2localpath(path))

        if result["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(result))


class GitLogHandler(GitHandler):
    """
    Handler for 'git log'.
    Fetches Commit SHA, Author Name, Commit Date & Commit Message.
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler,
        fetches Commit SHA, Author Name, Commit Date & Commit Message.
        """
        body = self.get_json_body()
        history_count = body.get("history_count", 25)
        follow_path = body.get("follow_path")
        result = await self.git.log(
            self.url2localpath(path), history_count, follow_path
        )

        if result["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(result))


class GitDetailedLogHandler(GitHandler):
    """
    Handler for 'git log -m --cc -1 --stat --numstat --oneline -z' command.
    Fetches file names of committed files, Number of insertions &
    deletions in that commit.
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler, fetches file names of committed files, Number of
        insertions & deletions in that commit.
        """
        data = self.get_json_body()
        selected_hash = data["selected_hash"]
        result = await self.git.detailed_log(selected_hash, self.url2localpath(path))

        if result["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(result))


class GitDiffHandler(GitHandler):
    """
    Handler for 'git diff --numstat'. Fetches changes between commits & working tree.
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler, fetches differences between two states
        tree.
        """
        data = self.get_json_body()

        if data:
            my_output = await self.git.diff(
                self.url2localpath(path),
                data.get("previous"),
                data.get("current"),
            )
        else:
            my_output = await self.git.diff(self.url2localpath(path))

        if my_output["code"] != 0:
            self.set_status(500)
        self.finish(my_output)


class GitBranchHandler(GitHandler):
    """
    Handler for 'git branch -a'. Fetches list of all branches in current repository
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler, fetches all branches in current repository.
        """
        result = await self.git.branch(self.url2localpath(path))

        if result["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(result))


class GitBranchDeleteHandler(GitHandler):
    """
    Handler for 'git branch -D <branch>'
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler, delete branch in current repository.

        Args:
            path: Git repository path relatively to the server root
        Body: {
            "branch": Branch name to be deleted
        }
        """
        data = self.get_json_body()
        result = await self.git.branch_delete(self.url2localpath(path), data["branch"])

        if result["code"] != 0:
            self.set_status(500)
            self.finish(json.dumps(result))
        else:
            self.set_status(204)


class GitAddHandler(GitHandler):
    """
    Handler for git add <filename>'.
    Adds one or all files to the staging area.
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler, adds one or all files into the staging area.
        """
        data = self.get_json_body()
        if data["add_all"]:
            body = await self.git.add_all(self.url2localpath(path))
        else:
            filename = data["filename"]
            body = await self.git.add(filename, self.url2localpath(path))

        if body["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(body))


class GitAddAllUnstagedHandler(GitHandler):
    """
    Handler for 'git add -u'. Adds ONLY all unstaged files, does not touch
    untracked or staged files.
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler, adds all the changed files.
        """
        body = await self.git.add_all_unstaged(self.url2localpath(path))
        if body["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(body))


class GitAddAllUntrackedHandler(GitHandler):
    """
    Handler for 'echo "a\n*\nq\n" | git add -i'. Adds ONLY all
    untracked files, does not touch unstaged or staged files.
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler, adds all the untracked files.
        """
        body = await self.git.add_all_untracked(self.url2localpath(path))
        if body["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(body))


class GitRemoteAddHandler(GitHandler):
    """Handler for 'git remote add <name> <url>'."""

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """POST request handler to add a remote."""
        data = self.get_json_body()
        name = data.get("name", DEFAULT_REMOTE_NAME)
        url = data["url"]
        output = await self.git.remote_add(self.url2localpath(path), url, name)
        if output["code"] == 0:
            self.set_status(201)
        else:
            self.set_status(500)
        self.finish(json.dumps(output))


class GitRemoteDetailsShowHandler(GitHandler):
    """Handler for 'git remote -v'."""

    @tornado.web.authenticated
    async def get(self, path: str = ""):
        """GET request handler to retrieve existing remotes."""
        local_path = self.url2localpath(path)
        output = await self.git.remote_show(local_path, verbose=True)
        if output["code"] == 0:
            self.set_status(200)
        else:
            self.set_status(500)
        self.finish(json.dumps(output))


class GitRemoteRemoveHandler(GitHandler):
    """Handler for 'git remote remove <name>'."""

    @tornado.web.authenticated
    async def delete(self, path: str = "", name: str = ""):
        """DELETE request handler to remove a remote."""
        local_path = self.url2localpath(path)

        output = await self.git.remote_remove(local_path, name)
        if output["code"] == 0:
            self.set_status(204)
        else:
            self.set_status(500)
            self.finish(json.dumps(output))


class GitResetHandler(GitHandler):
    """
    Handler for 'git reset <filename>'.
    Moves one or all files from the staged to the unstaged area.
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler,
        moves one or all files from the staged to the unstaged area.
        """
        data = self.get_json_body()
        local_path = self.url2localpath(path)
        if data["reset_all"]:
            body = await self.git.reset_all(local_path)
        else:
            filename = data["filename"]
            body = await self.git.reset(filename, local_path)

        if body["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(body))


class GitDeleteCommitHandler(GitHandler):
    """
    Handler for 'git revert --no-commit <SHA>'.
    Deletes the specified commit from the repository, leaving history intact.
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        data = self.get_json_body()
        commit_id = data["commit_id"]
        body = await self.git.delete_commit(commit_id, self.url2localpath(path))

        if body["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(body))


class GitResetToCommitHandler(GitHandler):
    """
    Handler for 'git reset --hard <SHA>'.
    Deletes all commits from head to the specified commit, making the specified commit the new head.
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        data = self.get_json_body()
        commit_id = data["commit_id"]
        body = await self.git.reset_to_commit(commit_id, self.url2localpath(path))

        if body["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(body))


class GitCheckoutHandler(GitHandler):
    """
    Handler for 'git checkout <branchname>'. Changes the current working branch.
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler, changes between branches.
        """
        data = self.get_json_body()
        local_path = self.url2localpath(path)

        if data["checkout_branch"]:
            if data["new_check"]:
                #  Need to check if startpoint is valid
                is_start_point_valid = await self.git._get_branch_reference(
                    data["startpoint"], local_path
                )

                #  If start point is not valid, we need to make an empty commit
                if not is_start_point_valid:
                    await self.git._empty_commit(local_path)

                body = await self.git.checkout_new_branch(
                    data["branchname"], data["startpoint"], local_path
                )
            else:
                body = await self.git.checkout_branch(data["branchname"], local_path)
        elif data["checkout_all"]:
            body = await self.git.checkout_all(local_path)
        else:
            body = await self.git.checkout(data["filename"], local_path)

        if body["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(body))


class GitMergeHandler(GitHandler):
    """
    Handler for git merge '<merge_from> <merge_into>'. Merges into current working branch
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler, merges branches
        """
        data = self.get_json_body()
        branch = data["branch"]
        body = await self.git.merge(branch, self.url2localpath(path))

        if body["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(body))


class GitCommitHandler(GitHandler):
    """
    Handler for 'git commit -m <message>' and 'git commit --amend'. Commits files.
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler, commits files.
        """
        data = self.get_json_body()
        commit_msg = data["commit_msg"]
        amend = data.get("amend", False)
        author = data.get("author")
        body = await self.git.commit(
            commit_msg, amend, self.url2localpath(path), author
        )

        if body["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(body))


class GitUpstreamHandler(GitHandler):
    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        Handler for the `git rev-parse --abbrev-ref $CURRENT_BRANCH_NAME@{upstream}` on the repo. Used to check if there
        is a upstream branch defined for the current Git repo (and a side-effect is disabling the Git push/pull actions)
        """
        local_path = self.url2localpath(path)
        current_branch = await self.git.get_current_branch(local_path)
        response = await self.git.get_upstream_branch(local_path, current_branch)
        if response["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(response))


class GitPullHandler(GitHandler):
    """
    Handler for 'git pull'. Pulls files from a remote branch.
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler, pulls files from a remote branch to your current branch.
        """
        data = self.get_json_body()
        response = await self.git.pull(
            self.url2localpath(path),
            data.get("auth", None),
            data.get("cancel_on_conflict", False),
        )

        if response["code"] != 0:
            self.set_status(500)

        self.finish(json.dumps(response))


class GitPushHandler(GitHandler):
    """
    Handler for 'git push <first-branch> <second-branch>.
    Pushes committed files to a remote branch.
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler,
        pushes committed files from your current branch to a remote branch

        Request body:
        {
            remote?: string # Remote to push to; i.e. <remote_name> or <remote_name>/<branch>
            force: boolean # Whether or not to force the push
        }
        """
        local_path = self.url2localpath(path)
        data = self.get_json_body()
        known_remote = data.get("remote")
        force = data.get("force", False)

        current_local_branch = await self.git.get_current_branch(local_path)

        set_upstream = False
        current_upstream_branch = await self.git.get_upstream_branch(
            local_path, current_local_branch
        )

        if known_remote is not None:
            set_upstream = current_upstream_branch["code"] != 0

            remote_name, _, remote_branch = known_remote.partition("/")

            current_upstream_branch = {
                "code": 0,
                "remote_branch": remote_branch or current_local_branch,
                "remote_short_name": remote_name,
            }

        if current_upstream_branch["code"] == 0:
            branch = ":".join(["HEAD", current_upstream_branch["remote_branch"]])
            response = await self.git.push(
                current_upstream_branch["remote_short_name"],
                branch,
                local_path,
                data.get("auth", None),
                set_upstream,
                force,
            )

        else:
            # Allow users to specify upstream through their configuration
            # https://git-scm.com/docs/git-config#Documentation/git-config.txt-pushdefault
            # Or use the remote defined if only one remote exists
            config = await self.git.config(local_path)
            config_options = config["options"]
            list_remotes = await self.git.remote_show(local_path)
            remotes = list_remotes.get("remotes", list())
            push_default = config_options.get("remote.pushdefault")

            default_remote = None
            if push_default is not None and push_default in remotes:
                default_remote = push_default
            elif len(remotes) == 1:
                default_remote = remotes[0]

            if default_remote is not None:
                response = await self.git.push(
                    default_remote,
                    current_local_branch,
                    local_path,
                    data.get("auth", None),
                    set_upstream=True,
                    force=force,
                )
            else:
                response = {
                    "code": 128,
                    "message": "fatal: The current branch {} has no upstream branch.".format(
                        current_local_branch
                    ),
                    "remotes": remotes,  # Returns the list of known remotes
                }

        if response["code"] != 0:
            self.set_status(500)

        self.finish(json.dumps(response))


class GitInitHandler(GitHandler):
    """
    Handler for 'git init'. Initializes a repository.
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler, initializes a repository.
        """
        body = await self.git.init(self.url2localpath(path))

        if body["code"] == 0:
            body = await self.git._empty_commit(self.url2localpath(path))

        if body["code"] != 0:
            self.set_status(500)

        self.finish(json.dumps(body))


class GitChangedFilesHandler(GitHandler):
    @tornado.web.authenticated
    async def post(self, path: str = ""):
        body = await self.git.changed_files(
            self.url2localpath(path), **self.get_json_body()
        )

        if body["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(body))


class GitConfigHandler(GitHandler):
    """
    Handler for 'git config' commands
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST get (if no options are passed) or set configuration options
        """
        data = self.get_json_body() or {}
        options = data.get("options", {})

        filtered_options = {k: v for k, v in options.items() if k in ALLOWED_OPTIONS}
        response = await self.git.config(self.url2localpath(path), **filtered_options)
        if "options" in response:
            response["options"] = {
                k: v for k, v in response["options"].items() if k in ALLOWED_OPTIONS
            }

        if response["code"] != 0:
            self.set_status(500)
        else:
            self.set_status(201)
        self.finish(json.dumps(response))


class GitContentHandler(GitHandler):
    """
    Handler to get file content at a certain git reference
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        data = self.get_json_body()
        filename = data["filename"]
        reference = data["reference"]
        local_path, cm = self.url2localpath(path, with_contents_manager=True)
        response = await self.git.get_content_at_reference(
            filename, reference, local_path, cm
        )
        self.finish(json.dumps(response))


class GitDiffNotebookHandler(GitHandler):
    """
    Returns nbdime diff of given notebook base content and remote content
    """

    @tornado.web.authenticated
    async def post(self):
        data = self.get_json_body()
        try:
            prev_content = data["previousContent"]
            curr_content = data["currentContent"]
        except KeyError as e:
            get_logger().error(f"Missing key in POST request.", exc_info=e)
            raise tornado.web.HTTPError(
                status_code=400, reason=f"Missing POST key: {e}"
            )
        try:
            base_content = data.get("baseContent")
            content = await self.git.get_nbdiff(
                prev_content, curr_content, base_content
            )
        except Exception as e:
            get_logger().error(f"Error computing notebook diff.", exc_info=e)
            raise tornado.web.HTTPError(
                status_code=500,
                reason=f"Error diffing content: {e}.",
            ) from e
        self.finish(json.dumps(content))


class GitIgnoreHandler(GitHandler):
    """
    Handler to manage .gitignore
    """

    @tornado.web.authenticated
    async def get(self, path: str = ""):
        """
        GET read content in .gitignore
        """
        local_path = self.url2localpath(path)
        body = self.git.read_file(local_path + "/.gitignore")
        if body["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(body))

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST add entry in .gitignore
        """
        local_path = self.url2localpath(path)
        data = self.get_json_body()
        file_path = data.get("file_path", None)
        content = data.get("content", None)
        use_extension = data.get("use_extension", False)
        if content:
            body = await self.git.write_gitignore(local_path, content)
        elif file_path:
            if use_extension:
                suffixes = Path(file_path).suffixes
                if len(suffixes) > 0:
                    file_path = "**/*" + ".".join(suffixes)
            body = await self.git.ignore(local_path, file_path)
        else:
            body = await self.git.ensure_gitignore(local_path)
        if body["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(body))


class GitSettingsHandler(GitHandler):
    @tornado.web.authenticated
    async def get(self):
        jlab_version = self.get_query_argument("version", None)
        if jlab_version is not None:
            jlab_version = str(parse(jlab_version))
        git_version = None
        try:
            git_version = await self.git.version()
        except Exception as error:
            self.log.debug(
                "[jupyterlab_git] Failed to execute 'git' command: {!s}".format(error)
            )
        server_version = str(__version__)

        self.finish(
            json.dumps(
                {
                    "frontendVersion": jlab_version,
                    "gitVersion": git_version,
                    "serverVersion": server_version,
                }
            )
        )


class GitTagHandler(GitHandler):
    """
    Handler for 'git for-each-ref refs/tags'. Fetches list of all tags in current repository
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler, fetches all tags in current repository.
        """
        result = await self.git.tags(self.url2localpath(path))

        if result["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(result))


class GitTagCheckoutHandler(GitHandler):
    """
    Handler for 'git tag checkout '. Checkout the tag version of repo
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler, checkout the tag version to a branch.
        """
        data = self.get_json_body()
        tag = data["tag_id"]
        result = await self.git.tag_checkout(self.url2localpath(path), tag)

        if result["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(result))


class GitNewTagHandler(GitHandler):
    """
    Handler for 'git tag <tag_name> <commit_id>. Create new tag pointing to a specific commit.
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler, create a new tag pointing to a specific commit.
        """
        data = self.get_json_body()
        tag = data["tag_id"]
        commit = data["commit_id"]
        response = await self.git.set_tag(self.url2localpath(path), tag, commit)
        if response["code"] == 0:
            self.set_status(201)
        else:
            self.set_status(500)
        self.finish(json.dumps(response))


class GitRebaseHandler(GitHandler):
    """
    Handler for git rebase '<rebase_onto>'.
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler, rebase the current branch
        """
        data = self.get_json_body()
        branch = data.get("branch")
        action = data.get("action", "")
        if branch is not None:
            body = await self.git.rebase(branch, self.url2localpath(path))
        else:
            try:
                body = await self.git.resolve_rebase(
                    self.url2localpath(path), RebaseAction[action.upper()]
                )
            except KeyError:
                raise tornado.web.HTTPError(
                    status_code=404, reason=f"Unknown action '{action}'"
                )

        if body["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(body))


class GitStashHandler(GitHandler):
    """
    Handler for 'git stash'. Stores the changes in the current branch
    """

    @tornado.web.authenticated
    async def post(self, path: str = "", stashMsg: str = ""):
        """
        POST request handler for 'git stash'
        """
        local_path = self.url2localpath(path)
        data = self.get_json_body()

        response = await self.git.stash(local_path, data.get("stashMsg", ""))
        if response["code"] == 0:
            self.set_status(201)
        else:
            self.set_status(500)
            self.finish(json.dumps(response))

    @tornado.web.authenticated
    async def delete(self, path: str = ""):
        """
        DELETE request handler to clear a single stash or the entire stash list in a Git repository
        """
        local_path = self.url2localpath(path)
        stash_index = self.get_query_argument("stash_index", None)

        # Choose what to erase
        if (stash_index is None) and (stash_index != 0):
            response = await self.git.drop_stash(local_path)
        else:
            response = await self.git.drop_stash(local_path, stash_index)

        if response["code"] == 0:
            self.set_status(204)
            self.finish()
        else:
            self.set_status(500)
            self.finish(json.dumps(response))

    @tornado.web.authenticated
    async def get(self, path: str = ""):
        """
        GET request handler for 'git stash list'
        """
        # pass the path to the git stash so it knows where to stash
        local_path = self.url2localpath(path)
        index = self.get_query_argument("index", None)
        if index is None:
            response = await self.git.stash_list(local_path)
        else:
            response = await self.git.stash_show(local_path, int(index))

        if response["code"] == 0:
            self.set_status(200)
        else:
            self.set_status(500)
        self.finish(json.dumps(response))


class GitStashPopHandler(GitHandler):
    """
    Grab all the files affected by each git stash
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler to pop the latest stash unless an index was provided
        """
        local_path = self.url2localpath(path)
        data = self.get_json_body()

        response = await self.git.pop_stash(local_path, data.get("index"))

        if response["code"] == 0:
            self.set_status(204)
            self.finish()
        else:
            self.set_status(500)
            self.finish(json.dumps(response))


class GitStashApplyHandler(GitHandler):
    """
    Apply the latest stash to the repository.
    """

    @tornado.web.authenticated
    async def post(self, path: str = ""):
        """
        POST request handler to apply the latest stash unless an index was provided
        """
        local_path = self.url2localpath(path)
        data = self.get_json_body()
        response = await self.git.apply_stash(local_path, data.get("index"))

        if response["code"] == 0:
            self.set_status(201)
        else:
            self.set_status(500)
            self.finish(json.dumps(response))


class GitSubmodulesHandler(GitHandler):
    """
    Handler for 'git submodule status --recursive.
    Get a list of submodules in the repo.
    """

    @tornado.web.authenticated
    async def get(self, path: str = ""):
        """
        GET request handler, fetches all submodules in current repository.
        """
        result = await self.git.submodule(self.url2localpath(path))

        if result["code"] != 0:
            self.set_status(500)
        self.finish(json.dumps(result))


class SshHostHandler(SSHHandler):
    """
    Handler for checking if a host is known by SSH
    """

    @authorized
    @tornado.web.authenticated
    async def get(self):
        """
        GET request handler, check if the host is known by SSH
        """
        hostname = self.get_query_argument("hostname")
        is_known_host = self.ssh.is_known_host(hostname)
        self.set_status(200)
        self.finish(json.dumps(is_known_host))

    @authorized
    @tornado.web.authenticated
    async def post(self):
        data = self.get_json_body()
        hostname = data["hostname"]
        self.ssh.add_host(hostname)


class AuthStartFlowHandler(GitHandler):
    """
    Handler to start OAuth device flow for authentication providers.
    """

    @tornado.web.authenticated
    async def post(self):
        """
        POST request to start device flow for a provider.
        
        Input format:
            {
              'provider': 'github' | 'gitlab' | 'gitea',
              'base_url': 'https://gitlab.example.com' (optional, for self-hosted)
            }
        """
        data = self.get_json_body()
        provider_name = data.get("provider")
        base_url = data.get("base_url")

        try:
            kwargs = {}
            if base_url:
                kwargs["base_url"] = base_url

            provider = get_provider(provider_name, **kwargs)
            if not provider:
                self.set_status(400)
                self.finish(
                    json.dumps(
                        {
                            "code": -1,
                            "message": f"Unknown provider: {provider_name}",
                        }
                    )
                )
                return

            flow_data = await provider.start_device_flow()
            self.set_status(200)
            self.finish(
                json.dumps(
                    {
                        "code": 0,
                        "data": flow_data,
                    }
                )
            )
        except Exception as e:
            self.log.error(f"Failed to start auth flow: {e}")
            self.set_status(500)
            self.finish(
                json.dumps(
                    {
                        "code": -1,
                        "message": str(e),
                    }
                )
            )


class AuthPollTokenHandler(GitHandler):
    """
    Handler to poll for access token after user authorization.
    """

    @tornado.web.authenticated
    async def post(self):
        """
        POST request to poll for token.
        
        Input format:
            {
              'provider': 'github' | 'gitlab' | 'gitea',
              'device_code': '<device_code>',
              'interval': 5,
              'base_url': 'https://gitlab.example.com' (optional, for self-hosted)
            }
        """
        data = self.get_json_body()
        provider_name = data.get("provider")
        device_code = data.get("device_code")
        interval = data.get("interval", 5)
        base_url = data.get("base_url")

        try:
            kwargs = {}
            if base_url:
                kwargs["base_url"] = base_url

            provider = get_provider(provider_name, **kwargs)
            if not provider:
                self.set_status(400)
                self.finish(
                    json.dumps(
                        {
                            "code": -1,
                            "message": f"Unknown provider: {provider_name}",
                        }
                    )
                )
                return

            token = await provider.poll_for_token(device_code, interval)
            if token:
                # Validate and get username
                is_valid, username = await provider.validate_token(token)
                if is_valid:
                    # Store token
                    host = provider.get_git_credential_url("")
                    if not host:
                        # Extract from base_url or use default
                        if provider_name == "github":
                            host = "github.com"
                        elif provider_name == "gitlab":
                            host = "gitlab.com" if not base_url else base_url.replace("https://", "").replace("http://", "")
                        elif provider_name == "gitea":
                            host = base_url.replace("https://", "").replace("http://", "") if base_url else "gitea.com"

                    storage = get_token_storage()
                    storage.store_token(provider_name, host, username, token)

                    self.set_status(200)
                    self.finish(
                        json.dumps(
                            {
                                "code": 0,
                                "data": {
                                    "username": username,
                                    "host": host,
                                    "provider": provider_name,
                                },
                            }
                        )
                    )
                else:
                    self.set_status(500)
                    self.finish(
                        json.dumps(
                            {
                                "code": -1,
                                "message": "Token validation failed",
                            }
                        )
                    )
            else:
                self.set_status(408)  # Request Timeout
                self.finish(
                    json.dumps(
                        {
                            "code": -1,
                            "message": "Authorization timed out or was denied",
                        }
                    )
                )
        except Exception as e:
            self.log.error(f"Failed to poll for token: {e}")
            self.set_status(500)
            self.finish(
                json.dumps(
                    {
                        "code": -1,
                        "message": str(e),
                    }
                )
            )


class AuthStoreTokenHandler(GitHandler):
    """
    Handler to manually store a token (for Gitea/Forgejo).
    """

    @tornado.web.authenticated
    async def post(self):
        """
        POST request to store a token.
        
        Input format:
            {
              'provider': 'github' | 'gitlab' | 'gitea',
              'host': 'github.com',
              'username': 'user',
              'token': '<access_token>'
            }
        """
        data = self.get_json_body()
        provider_name = data.get("provider")
        host = data.get("host")
        username = data.get("username")
        token = data.get("token")

        if not all([provider_name, host, username, token]):
            self.set_status(400)
            self.finish(
                json.dumps(
                    {
                        "code": -1,
                        "message": "Missing required fields",
                    }
                )
            )
            return

        try:
            # Validate token with provider
            base_url = f"https://{host}" if not host.startswith("http") else host
            provider = get_provider(provider_name, base_url=base_url)
            if not provider:
                self.set_status(400)
                self.finish(
                    json.dumps(
                        {
                            "code": -1,
                            "message": f"Unknown provider: {provider_name}",
                        }
                    )
                )
                return

            is_valid, validated_username = await provider.validate_token(token)
            if not is_valid:
                self.set_status(400)
                self.finish(
                    json.dumps(
                        {
                            "code": -1,
                            "message": "Invalid token",
                        }
                    )
                )
                return

            # Store token
            storage = get_token_storage()
            success = storage.store_token(provider_name, host, username, token)

            if success:
                self.set_status(200)
                self.finish(
                    json.dumps(
                        {
                            "code": 0,
                            "data": {
                                "username": validated_username or username,
                                "host": host,
                                "provider": provider_name,
                            },
                        }
                    )
                )
            else:
                self.set_status(500)
                self.finish(
                    json.dumps(
                        {
                            "code": -1,
                            "message": "Failed to store token",
                        }
                    )
                )
        except Exception as e:
            self.log.error(f"Failed to store token: {e}")
            self.set_status(500)
            self.finish(
                json.dumps(
                    {
                        "code": -1,
                        "message": str(e),
                    }
                )
            )


class AuthGetTokenHandler(GitHandler):
    """
    Handler to retrieve stored token for a provider/host.
    """

    @tornado.web.authenticated
    async def post(self):
        """
        POST request to get token.
        
        Input format:
            {
              'provider': 'github' | 'gitlab' | 'gitea',
              'host': 'github.com'
            }
        """
        data = self.get_json_body()
        provider_name = data.get("provider")
        host = data.get("host")

        if not all([provider_name, host]):
            self.set_status(400)
            self.finish(
                json.dumps(
                    {
                        "code": -1,
                        "message": "Missing required fields",
                    }
                )
            )
            return

        try:
            storage = get_token_storage()
            credential = storage.get_token(provider_name, host)

            if credential:
                self.set_status(200)
                self.finish(
                    json.dumps(
                        {
                            "code": 0,
                            "data": {
                                "username": credential.get("username"),
                                "has_token": True,
                            },
                        }
                    )
                )
            else:
                self.set_status(404)
                self.finish(
                    json.dumps(
                        {
                            "code": -1,
                            "message": "No token found",
                        }
                    )
                )
        except Exception as e:
            self.log.error(f"Failed to get token: {e}")
            self.set_status(500)
            self.finish(
                json.dumps(
                    {
                        "code": -1,
                        "message": str(e),
                    }
                )
            )


class AuthDeleteTokenHandler(GitHandler):
    """
    Handler to delete stored token (logout).
    """

    @tornado.web.authenticated
    async def post(self):
        """
        POST request to delete token.
        
        Input format:
            {
              'provider': 'github' | 'gitlab' | 'gitea',
              'host': 'github.com'
            }
        """
        data = self.get_json_body()
        provider_name = data.get("provider")
        host = data.get("host")

        if not all([provider_name, host]):
            self.set_status(400)
            self.finish(
                json.dumps(
                    {
                        "code": -1,
                        "message": "Missing required fields",
                    }
                )
            )
            return

        try:
            storage = get_token_storage()
            success = storage.delete_token(provider_name, host)

            if success:
                self.set_status(200)
                self.finish(
                    json.dumps(
                        {
                            "code": 0,
                            "message": "Token deleted successfully",
                        }
                    )
                )
            else:
                self.set_status(500)
                self.finish(
                    json.dumps(
                        {
                            "code": -1,
                            "message": "Failed to delete token",
                        }
                    )
                )
        except Exception as e:
            self.log.error(f"Failed to delete token: {e}")
            self.set_status(500)
            self.finish(
                json.dumps(
                    {
                        "code": -1,
                        "message": str(e),
                    }
                )
            )


class AuthListTokensHandler(GitHandler):
    """
    Handler to list all stored tokens.
    """

    @tornado.web.authenticated
    async def get(self):
        """
        GET request to list all stored tokens.
        """
        try:
            storage = get_token_storage()
            tokens = storage.list_tokens()

            self.set_status(200)
            self.finish(
                json.dumps(
                    {
                        "code": 0,
                        "data": tokens,
                    }
                )
            )
        except Exception as e:
            self.log.error(f"Failed to list tokens: {e}")
            self.set_status(500)
            self.finish(
                json.dumps(
                    {
                        "code": -1,
                        "message": str(e),
                    }
                )
            )


def setup_handlers(web_app):
    """
    Setups all of the git command handlers.
    Every handler is defined here, to be used in git.py file.
    """

    handlers_with_path = [
        ("/add_all_unstaged", GitAddAllUnstagedHandler),
        ("/add_all_untracked", GitAddAllUntrackedHandler),
        ("/all_history", GitAllHistoryHandler),
        ("/branch/delete", GitBranchDeleteHandler),
        ("/branch", GitBranchHandler),
        ("/changed_files", GitChangedFilesHandler),
        ("/checkout", GitCheckoutHandler),
        ("/clone", GitCloneHandler),
        ("/commit", GitCommitHandler),
        ("/config", GitConfigHandler),
        ("/content", GitContentHandler),
        ("/delete_commit", GitDeleteCommitHandler),
        ("/detailed_log", GitDetailedLogHandler),
        ("/diff", GitDiffHandler),
        ("/init", GitInitHandler),
        ("/log", GitLogHandler),
        ("/merge", GitMergeHandler),
        ("/pull", GitPullHandler),
        ("/push", GitPushHandler),
        ("/remote/add", GitRemoteAddHandler),
        ("/remote/fetch", GitFetchHandler),
        ("/remote/show", GitRemoteDetailsShowHandler),
        ("/reset", GitResetHandler),
        ("/reset_to_commit", GitResetToCommitHandler),
        ("/show_prefix", GitShowPrefixHandler),
        ("/show_top_level", GitShowTopLevelHandler),
        ("/status", GitStatusHandler),
        ("/upstream", GitUpstreamHandler),
        ("/ignore", GitIgnoreHandler),
        ("/tags", GitTagHandler),
        ("/tag_checkout", GitTagCheckoutHandler),
        ("/tag", GitNewTagHandler),
        ("/add", GitAddHandler),
        ("/rebase", GitRebaseHandler),
        ("/stash", GitStashHandler),
        ("/stash_pop", GitStashPopHandler),
        ("/stash_apply", GitStashApplyHandler),
        ("/submodules", GitSubmodulesHandler),
    ]

    handlers = [
        ("/diffnotebook", GitDiffNotebookHandler),
        ("/settings", GitSettingsHandler),
        ("/known_hosts", SshHostHandler),
        ("/auth/start_flow", AuthStartFlowHandler),
        ("/auth/poll_token", AuthPollTokenHandler),
        ("/auth/store_token", AuthStoreTokenHandler),
        ("/auth/get_token", AuthGetTokenHandler),
        ("/auth/delete_token", AuthDeleteTokenHandler),
        ("/auth/list_tokens", AuthListTokensHandler),
    ]

    # add the baseurl to our paths
    base_url = web_app.settings["base_url"]
    git_handlers = (
        [
            (url_path_join(base_url, NAMESPACE + path_regex + endpoint), handler)
            for endpoint, handler in handlers_with_path
        ]
        + [
            (url_path_join(base_url, NAMESPACE + endpoint), handler)
            for endpoint, handler in handlers
        ]
        + [
            (
                url_path_join(
                    base_url, NAMESPACE + path_regex + r"/remote/(?P<name>\w+)"
                ),
                GitRemoteRemoveHandler,
            )
        ]
    )

    web_app.add_handlers(".*", git_handlers)
