import functools
from collections.abc import Iterable
from typing import Sequence

from decorators.database import begin_session
from models.collection import Collection, VirtualCollection
from models.rom import Rom, RomFile, RomUser
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import Query, Session, selectinload

from .base_handler import DBBaseHandler


def with_details(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        session = kwargs.get("session")
        if session is None:
            raise TypeError(
                f"{func} is missing required kwarg 'session' with type 'Session'"
            )

        kwargs["query"] = select(Rom).options(
            selectinload(Rom.saves),
            selectinload(Rom.states),
            selectinload(Rom.screenshots),
            selectinload(Rom.rom_users),
            selectinload(Rom.sibling_roms),
            selectinload(Rom.collections),
        )
        return func(*args, **kwargs)

    return wrapper


def with_simple(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        session = kwargs.get("session")
        if session is None:
            raise TypeError(
                f"{func} is missing required kwarg 'session' with type 'Session'"
            )

        kwargs["query"] = select(Rom).options(
            selectinload(Rom.rom_users), selectinload(Rom.sibling_roms)
        )
        return func(*args, **kwargs)

    return wrapper


class DBRomsHandler(DBBaseHandler):
    def _filter(
        self,
        data,
        platform_id: int | None,
        collection_id: int | None,
        virtual_collection_id: str | None,
        search_term: str | None,
        session: Session,
    ):
        if platform_id:
            data = data.filter(Rom.platform_id == platform_id)

        if collection_id:
            collection = (
                session.query(Collection)
                .filter(Collection.id == collection_id)
                .one_or_none()
            )
            if collection:
                data = data.filter(Rom.id.in_(collection.rom_ids))

        if virtual_collection_id:
            name, type = VirtualCollection.from_id(virtual_collection_id)
            v_collection = (
                session.query(VirtualCollection)
                .filter(VirtualCollection.name == name, VirtualCollection.type == type)
                .one_or_none()
            )
            if v_collection:
                data = data.filter(Rom.id.in_(v_collection.rom_ids))

        if search_term is not None:
            data = data.filter(
                or_(
                    Rom.fs_name.ilike(f"%{search_term}%"),
                    Rom.name.ilike(f"%{search_term}%"),
                )
            )

        return data

    def _order(self, data, order_by: str, order_dir: str):
        if order_by == "id":
            _column = Rom.id
        else:
            _column = func.lower(Rom.name)

        if order_dir == "desc":
            return data.order_by(_column.desc())
        else:
            return data.order_by(_column.asc())

    @begin_session
    @with_details
    def add_rom(self, rom: Rom, query: Query = None, session: Session = None) -> Rom:
        rom = session.merge(rom)
        session.flush()

        return session.scalar(query.filter_by(id=rom.id).limit(1))

    @begin_session
    @with_details
    def get_rom(
        self, id: int, *, query: Query = None, session: Session = None
    ) -> Rom | None:
        return session.scalar(query.filter_by(id=id).limit(1))

    @begin_session
    @with_simple
    def get_roms(
        self,
        *,
        platform_id: int | None = None,
        collection_id: int | None = None,
        virtual_collection_id: str | None = None,
        search_term: str | None = None,
        order_by: str = "name",
        order_dir: str = "asc",
        limit: int | None = None,
        offset: int | None = None,
        query: Query = None,
        session: Session = None,
    ) -> Sequence[Rom]:
        filtered_query = self._filter(
            query,
            platform_id,
            collection_id,
            virtual_collection_id,
            search_term,
            session,
        )
        ordered_query = self._order(filtered_query, order_by, order_dir)
        offset_query = ordered_query.offset(offset)
        limited_query = offset_query.limit(limit)
        return session.scalars(limited_query).unique().all()

    @begin_session
    @with_details
    def get_rom_by_fs_name(
        self,
        platform_id: int,
        fs_name: str,
        query: Query = None,
        session: Session = None,
    ) -> Rom | None:
        return session.scalar(
            query.filter_by(platform_id=platform_id, fs_name=fs_name).limit(1)
        )

    @begin_session
    def get_roms_by_fs_name(
        self,
        platform_id: int,
        fs_names: Iterable[str],
        query: Query = None,
        session: Session = None,
    ) -> dict[str, Rom]:
        """Retrieve a dictionary of roms by their filesystem names."""
        query = query or select(Rom)
        roms = (
            session.scalars(
                query.filter(Rom.fs_name.in_(fs_names)).filter_by(
                    platform_id=platform_id
                )
            )
            .unique()
            .all()
        )
        return {rom.fs_name: rom for rom in roms}

    @begin_session
    @with_details
    def get_rom_by_fs_name_no_tags(
        self, fs_name_no_tags: str, query: Query = None, session: Session = None
    ) -> Rom | None:
        return session.scalar(query.filter_by(fs_name_no_tags=fs_name_no_tags).limit(1))

    @begin_session
    @with_details
    def get_rom_by_fs_name_no_ext(
        self, fs_name_no_ext: str, query: Query = None, session: Session = None
    ) -> Rom | None:
        return session.scalar(query.filter_by(fs_name_no_ext=fs_name_no_ext).limit(1))

    @begin_session
    def update_rom(self, id: int, data: dict, session: Session = None) -> Rom:
        session.execute(
            update(Rom)
            .where(Rom.id == id)
            .values(**data)
            .execution_options(synchronize_session="evaluate")
        )
        return session.query(Rom).filter_by(id=id).one()

    @begin_session
    def delete_rom(self, id: int, session: Session = None) -> None:
        session.execute(
            delete(Rom)
            .where(Rom.id == id)
            .execution_options(synchronize_session="evaluate")
        )

    @begin_session
    def purge_roms(
        self, platform_id: int, fs_roms_to_keep: list[str], session: Session = None
    ) -> Sequence[Rom]:
        purged_roms = (
            session.scalars(
                select(Rom)
                .order_by(Rom.fs_name.asc())
                .where(
                    and_(
                        Rom.platform_id == platform_id,
                        Rom.fs_name.not_in(fs_roms_to_keep),
                    )
                )
            )
            .unique()
            .all()
        )
        session.execute(
            delete(Rom)
            .where(
                and_(
                    Rom.platform_id == platform_id, Rom.fs_name.not_in(fs_roms_to_keep)
                )
            )
            .execution_options(synchronize_session="evaluate")
        )
        return purged_roms

    @begin_session
    def add_rom_user(
        self, rom_id: int, user_id: int, session: Session = None
    ) -> RomUser:
        return session.merge(RomUser(rom_id=rom_id, user_id=user_id))

    @begin_session
    def get_rom_user(
        self, rom_id: int, user_id: int, session: Session = None
    ) -> RomUser | None:
        return session.scalar(
            select(RomUser).filter_by(rom_id=rom_id, user_id=user_id).limit(1)
        )

    @begin_session
    @with_simple
    def get_roms_user(
        self,
        *,
        user_id: int,
        platform_id: int | None = None,
        collection_id: int | None = None,
        virtual_collection_id: str | None = None,
        search_term: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        query: Query = None,
        session: Session = None,
    ) -> Sequence[Rom]:
        filtered_query = (
            query.join(RomUser)
            .filter(RomUser.user_id == user_id)
            .order_by(RomUser.last_played.desc())
        )
        filtered_query = self._filter(
            filtered_query,
            platform_id,
            collection_id,
            virtual_collection_id,
            search_term,
            session,
        )
        offset_query = filtered_query.offset(offset)
        limited_query = offset_query.limit(limit)
        return session.scalars(limited_query).unique().all()

    @begin_session
    def get_rom_user_by_id(self, id: int, session: Session = None) -> RomUser | None:
        return session.scalar(select(RomUser).filter_by(id=id).limit(1))

    @begin_session
    def update_rom_user(
        self, id: int, data: dict, session: Session = None
    ) -> RomUser | None:
        session.execute(
            update(RomUser)
            .where(RomUser.id == id)
            .values(**data)
            .execution_options(synchronize_session="evaluate")
        )

        rom_user = self.get_rom_user_by_id(id)
        if not rom_user:
            return None

        if not data.get("is_main_sibling", False):
            return rom_user

        rom = self.get_rom(rom_user.rom_id)
        if not rom:
            return rom_user

        session.execute(
            update(RomUser)
            .where(
                and_(
                    RomUser.rom_id.in_(r.id for r in rom.sibling_roms),
                    RomUser.user_id == rom_user.user_id,
                )
            )
            .values(is_main_sibling=False)
        )

        return session.query(RomUser).filter_by(id=id).one()

    @begin_session
    def add_rom_file(self, rom_file: RomFile, session: Session = None) -> RomFile:
        return session.merge(rom_file)

    @begin_session
    def get_rom_file_by_id(self, id: int, session: Session = None) -> RomFile | None:
        return session.scalar(select(RomFile).filter_by(id=id).limit(1))

    @begin_session
    def update_rom_file(self, id: int, data: dict, session: Session = None) -> RomFile:
        session.execute(
            update(RomFile)
            .where(RomFile.id == id)
            .values(**data)
            .execution_options(synchronize_session="evaluate")
        )

        return session.query(RomFile).filter_by(id=id).one()

    @begin_session
    def purge_rom_files(
        self, rom_id: int, session: Session = None
    ) -> Sequence[RomFile]:
        purged_rom_files = (
            session.scalars(select(RomFile).filter_by(rom_id=rom_id)).unique().all()
        )
        session.execute(
            delete(RomFile)
            .where(RomFile.rom_id == rom_id)
            .execution_options(synchronize_session="evaluate")
        )
        return purged_rom_files
